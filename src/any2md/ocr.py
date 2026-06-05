from __future__ import annotations

import base64
import json
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from any2md.errors import OcrNotConfiguredError, OcrRequestError


class OcrEngine(Protocol):
    def extract_text(self, path: Path) -> str: ...


DEFAULT_OCR_PROMPT = (
    "请识别图片中的所有可见文字，并尽量按原始版式整理成 Markdown。"
    "如果图片中存在标题、列表、表格、代码块或引用，请使用对应的 Markdown 语法表达；"
    "仅返回 Markdown 正文，不要添加解释、前言、结语或代码围栏；"
    "不要猜测图片中不存在的内容；无法辨认时保留原样或留空。"
)


@dataclass(slots=True, frozen=True)
class LlmOcrSettings:
    api_base: str
    api_key: str
    model: str
    timeout: float = 60.0
    prompt: str = DEFAULT_OCR_PROMPT
    api_type: str | None = None  # "openai", "anthropic", or "glm_ocr"; auto-detected if None


def load_env_file(env_path: Path | None = None, *, override: bool = False) -> dict[str, str]:
    target = env_path or Path.cwd() / ".env"
    if not target.exists() or not target.is_file():
        return {}

    loaded: dict[str, str] = {}
    for raw_line in target.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        if not key:
            continue

        normalized_value = _normalize_env_value(value.strip())
        if override or key not in os.environ:
            os.environ[key] = normalized_value
            loaded[key] = normalized_value

    return loaded


def resolve_llm_ocr_settings(
    *,
    env_path: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> LlmOcrSettings:
    if environ is None:
        load_env_file(env_path)
        source: Mapping[str, str] = os.environ
    else:
        source = environ

    api_base = _first_value(source, "ANY2MD_LLM_API_BASE", "LLM_API_BASE", "OPENAI_BASE_URL")
    api_key = _first_value(source, "ANY2MD_LLM_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY")
    model = _first_value(source, "ANY2MD_LLM_MODEL", "LLM_MODEL", "OPENAI_MODEL")
    timeout_value = _first_value(source, "ANY2MD_LLM_TIMEOUT", "LLM_TIMEOUT")
    prompt = _first_value(source, "ANY2MD_OCR_PROMPT", "OCR_PROMPT") or DEFAULT_OCR_PROMPT
    api_type = _first_value(source, "ANY2MD_LLM_API_TYPE", "LLM_API_TYPE") or None

    missing = [
        name
        for name, value in {
            "ANY2MD_LLM_API_BASE": api_base,
            "ANY2MD_LLM_API_KEY": api_key,
            "ANY2MD_LLM_MODEL": model,
        }.items()
        if not value
    ]
    if missing:
        joined = ", ".join(missing)
        raise OcrNotConfiguredError(
            "OCR 未配置。请在 .env 中设置以下变量："
            f"{joined}"
        )

    timeout = 60.0
    if timeout_value:
        try:
            timeout = float(timeout_value)
        except ValueError as exc:
            raise OcrNotConfiguredError(
                "OCR 超时时间配置无效，请将 ANY2MD_LLM_TIMEOUT 设置为数字。"
            ) from exc

    # Validate api_type if provided
    if api_type and api_type not in ("openai", "anthropic", "glm_ocr"):
        raise OcrNotConfiguredError(
            f"无效的 API 类型：{api_type}。请设置为 'openai'、'anthropic' 或 'glm_ocr'。"
        )

    return LlmOcrSettings(
        api_base=api_base,
        api_key=api_key,
        model=model,
        timeout=timeout,
        prompt=prompt,
        api_type=api_type,
    )


class LlmVisionOcrEngine:
    def __init__(
        self,
        settings: LlmOcrSettings | None = None,
        *,
        env_path: Path | None = None,
        http_client: Callable[..., object] = urlopen,
    ) -> None:
        self._settings = settings
        self._env_path = env_path
        self._http_client = http_client

    def extract_text(self, path: Path) -> str:
        settings = self._settings or resolve_llm_ocr_settings(env_path=self._env_path)

        # Detect API type
        api_type = settings.api_type or _detect_api_type(settings.api_base, settings.model)

        request = self._build_request(path=path, settings=settings, api_type=api_type)

        try:
            with self._http_client(request, timeout=settings.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore") if hasattr(exc, "read") else ""
            raise OcrRequestError(
                f"OCR 请求失败，HTTP {exc.code}：{detail or exc.reason}"
            ) from exc
        except URLError as exc:
            raise OcrRequestError(f"OCR 请求失败：{exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise OcrRequestError("OCR 响应不是合法的 JSON。") from exc

        markdown = _extract_message_content(payload, api_type)
        if not markdown:
            raise OcrRequestError("OCR 响应中没有可用内容。")
        return _strip_markdown_fence(markdown)

    def _build_request(self, *, path: Path, settings: LlmOcrSettings, api_type: str) -> Request:
        image_bytes = path.read_bytes()
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        encoded_image = base64.b64encode(image_bytes).decode("ascii")

        endpoint = _resolve_api_endpoint(settings.api_base, api_type)
        payload = _build_api_payload(settings, encoded_image, mime_type, api_type)
        headers = _build_api_headers(settings.api_key, api_type)

        body = json.dumps(payload).encode("utf-8")
        return Request(
            endpoint,
            data=body,
            headers=headers,
            method="POST",
        )


def build_default_ocr_engine(env_path: Path | None = None) -> OcrEngine:
    return LlmVisionOcrEngine(env_path=env_path)


def _first_value(source: Mapping[str, str], *keys: str) -> str:
    for key in keys:
        value = source.get(key, "").strip()
        if value:
            return value
    return ""


def _normalize_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _detect_api_type(api_base: str, model: str) -> str:
    """Detect API type from base URL or model name."""
    normalized = api_base.lower()

    # Check URL patterns
    if "layout_parsing" in normalized:
        return "glm_ocr"
    if "anthropic" in normalized or "claude" in normalized:
        return "anthropic"

    # Check model name patterns
    model_lower = model.lower()
    if model_lower == "glm-ocr":
        return "glm_ocr"
    if model_lower.startswith("claude"):
        return "anthropic"

    # Default to OpenAI-compatible
    return "openai"


def _resolve_api_endpoint(api_base: str, api_type: str) -> str:
    """Resolve the correct API endpoint based on API type."""
    normalized = api_base.rstrip("/")

    if api_type == "glm_ocr":
        if normalized.endswith("/paas/v4/layout_parsing"):
            return normalized
        if normalized.endswith("/api"):
            return f"{normalized}/paas/v4/layout_parsing"
        return f"{normalized}/api/paas/v4/layout_parsing"

    if api_type == "anthropic":
        # Anthropic uses /v1/messages or /v1/responses
        if normalized.endswith("/messages") or normalized.endswith("/responses"):
            return normalized
        if normalized.endswith("/v1"):
            return f"{normalized}/messages"
        return f"{normalized}/v1/messages"

    # OpenAI-compatible format
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def _build_api_payload(
    settings: LlmOcrSettings,
    encoded_image: str,
    mime_type: str,
    api_type: str,
) -> dict:
    """Build API request payload based on API type."""
    if api_type == "glm_ocr":
        return {
            "model": settings.model,
            "file": f"data:{mime_type};base64,{encoded_image}",
        }

    if api_type == "anthropic":
        # Anthropic Messages API format
        return {
            "model": settings.model,
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": settings.prompt},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": encoded_image,
                            },
                        },
                    ],
                }
            ],
        }

    # OpenAI-compatible format
    return {
        "model": settings.model,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": settings.prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{encoded_image}"
                        },
                    },
                ],
            }
        ],
    }


def _build_api_headers(api_key: str, api_type: str) -> dict[str, str]:
    """Build API request headers based on API type."""
    if api_type == "anthropic":
        return {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }

    # OpenAI-compatible format
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }


def _extract_message_content(payload: dict[str, object], api_type: str) -> str:
    """Extract text content from API response based on API type."""
    if api_type == "glm_ocr":
        content = payload.get("md_results")
        return content.strip() if isinstance(content, str) else ""

    if api_type == "anthropic":
        # Anthropic Messages API response format
        content = payload.get("content")
        if not isinstance(content, list) or not content:
            return ""

        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if isinstance(text, str):
                    parts.append(text.strip())

        return "\n".join(parts).strip()

    # OpenAI-compatible format
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""

    message = first_choice.get("message")
    if not isinstance(message, dict):
        return ""

    content = message.get("content")
    if isinstance(content, str):
        return content.strip()

    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(item.get("text", "")).strip()
        else:
            text = ""
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _strip_markdown_fence(content: str) -> str:
    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if len(lines) < 3 or lines[-1].strip() != "```":
        return stripped

    body = lines[1:-1]
    if body and body[0].strip().lower() in {"markdown", "md"}:
        body = body[1:]
    return "\n".join(body).strip()
