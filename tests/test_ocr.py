import json
import os
import shutil
import unittest
import uuid
from pathlib import Path

import tests._bootstrap
from any2md.errors import OcrNotConfiguredError
from any2md.ocr import LlmOcrSettings, LlmVisionOcrEngine, load_env_file, resolve_llm_ocr_settings


class FakeHttpResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


class OcrTests(unittest.TestCase):
    def test_load_env_file_reads_dotenv_values(self) -> None:
        case_dir = _make_case_dir()
        try:
            env_path = case_dir / ".env"
            env_path.write_text(
                "ANY2MD_LLM_API_BASE=https://example.com/v1\n"
                "ANY2MD_LLM_API_KEY='secret-key'\n"
                'ANY2MD_LLM_MODEL="gpt-4.1-mini"\n',
                encoding="utf-8",
            )

            original = {key: os.environ.get(key) for key in _tracked_env_keys()}
            try:
                for key in _tracked_env_keys():
                    os.environ.pop(key, None)
                loaded = load_env_file(env_path)
            finally:
                _restore_env(original)
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)

        self.assertEqual(loaded["ANY2MD_LLM_API_KEY"], "secret-key")
        self.assertEqual(loaded["ANY2MD_LLM_MODEL"], "gpt-4.1-mini")

    def test_load_env_file_supports_utf8_bom(self) -> None:
        case_dir = _make_case_dir()
        try:
            env_path = case_dir / ".env"
            env_path.write_text(
                "ANY2MD_LLM_API_BASE=https://example.com/v1\n",
                encoding="utf-8-sig",
            )

            original = {key: os.environ.get(key) for key in _tracked_env_keys()}
            try:
                for key in _tracked_env_keys():
                    os.environ.pop(key, None)
                loaded = load_env_file(env_path)
            finally:
                _restore_env(original)
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)

        self.assertEqual(loaded["ANY2MD_LLM_API_BASE"], "https://example.com/v1")

    def test_resolve_llm_ocr_settings_requires_required_values(self) -> None:
        with self.assertRaises(OcrNotConfiguredError):
            resolve_llm_ocr_settings(environ={})

    def test_llm_ocr_engine_calls_openai_compatible_endpoint(self) -> None:
        captured: dict[str, object] = {}

        def fake_http_client(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["headers"] = dict(request.header_items())
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeHttpResponse({"choices": [{"message": {"content": "# 标题\n\n正文"}}]})

        settings = LlmOcrSettings(
            api_base="https://example.com/v1",
            api_key="secret-key",
            model="demo-model",
            timeout=12.5,
            prompt="请输出 Markdown",
        )

        case_dir = _make_case_dir()
        try:
            image_path = case_dir / "sample.png"
            image_path.write_bytes(b"fake-image")
            engine = LlmVisionOcrEngine(settings=settings, http_client=fake_http_client)

            result = engine.extract_text(image_path)
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)

        self.assertEqual(result, "# 标题\n\n正文")
        self.assertEqual(captured["url"], "https://example.com/v1/chat/completions")
        self.assertEqual(captured["timeout"], 12.5)
        self.assertEqual(captured["headers"]["Authorization"], "Bearer secret-key")
        payload = captured["payload"]
        self.assertEqual(payload["model"], "demo-model")
        self.assertEqual(payload["messages"][0]["content"][0]["text"], "请输出 Markdown")
        self.assertTrue(payload["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_llm_ocr_engine_supports_list_content_response(self) -> None:
        def fake_http_client(request, timeout):
            return FakeHttpResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": [
                                    {"type": "output_text", "text": "```markdown"},
                                    {"type": "output_text", "text": "# 标题\n\n正文"},
                                    {"type": "output_text", "text": "```"},
                                ]
                            }
                        }
                    ]
                }
            )

        settings = LlmOcrSettings(
            api_base="https://example.com",
            api_key="secret-key",
            model="demo-model",
        )

        case_dir = _make_case_dir()
        try:
            image_path = case_dir / "sample.jpg"
            image_path.write_bytes(b"fake-image")
            engine = LlmVisionOcrEngine(settings=settings, http_client=fake_http_client)

            result = engine.extract_text(image_path)
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)

        self.assertEqual(result, "# 标题\n\n正文")


def _tracked_env_keys() -> tuple[str, ...]:
    return (
        "ANY2MD_LLM_API_BASE",
        "ANY2MD_LLM_API_KEY",
        "ANY2MD_LLM_MODEL",
        "ANY2MD_LLM_TIMEOUT",
        "ANY2MD_OCR_PROMPT",
    )


def _restore_env(original: dict[str, str | None]) -> None:
    for key, value in original.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _make_case_dir() -> Path:
    case_dir = tests._bootstrap.TEST_TEMP_ROOT / f"ocr-{uuid.uuid4().hex}"
    case_dir.mkdir(parents=True, exist_ok=False)
    return case_dir
