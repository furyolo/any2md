from __future__ import annotations

import os
import re
import shlex
import subprocess
import tempfile
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from any2md.auc import AucClient, AucMarkdownRenderer
from any2md.auc.client import AucTask
from any2md.auc.errors import AucNotConfiguredError
from any2md.auc.settings import load_auc_settings
from any2md.auc.task_store import AucTaskStore
from any2md.errors import Any2MDError
from any2md.ocr import load_env_file


class MediaProcessingError(Any2MDError):
    """音频处理失败。"""


class AudioTaskPendingError(Any2MDError):
    def __init__(self, task: AucTask, audio_url: str, reason: str) -> None:
        self.task = task
        self.audio_url = audio_url
        self.reason = reason
        super().__init__(reason)


DEFAULT_QWEN3_ASR_PROMPT = "请逐字转写这段音频内容，只输出转写结果，不要添加解释或额外说明。"
DEFAULT_QWEN3_ASR_MODEL = "Qwen/Qwen3-ASR-1.7B"


@dataclass(slots=True, frozen=True)
class LocalQwenAudioSettings:
    runtime: str
    model: str
    executable: Path | None = None
    prompt: str = DEFAULT_QWEN3_ASR_PROMPT
    language: str = "auto"
    timeout_seconds: int = 3600
    command_template: str | None = None
    device_map: str = "cpu"
    dtype: str = "float32"
    max_new_tokens: int = 256
    max_inference_batch_size: int = 1


def resolve_local_qwen_audio_settings(
    *,
    runtime: str | None = None,
    executable: str | None = None,
    model: str | None = None,
    prompt: str | None = None,
    language: str | None = None,
    timeout_seconds: int | None = None,
    command_template: str | None = None,
    device_map: str | None = None,
    dtype: str | None = None,
    max_new_tokens: int | None = None,
    max_inference_batch_size: int | None = None,
    env_path: Path | None = None,
) -> LocalQwenAudioSettings:
    load_env_file(env_path)

    resolved_runtime = runtime or os.getenv("ANY2MD_QWEN_AUDIO_RUNTIME", "qwen-asr")
    resolved_executable = executable or os.getenv("ANY2MD_QWEN_AUDIO_EXECUTABLE")
    resolved_model = model or os.getenv("ANY2MD_QWEN_AUDIO_MODEL")
    if not resolved_model and resolved_runtime == "qwen-asr":
        resolved_model = DEFAULT_QWEN3_ASR_MODEL
    resolved_prompt = prompt or os.getenv("ANY2MD_QWEN_AUDIO_PROMPT") or DEFAULT_QWEN3_ASR_PROMPT
    resolved_language = language or os.getenv("ANY2MD_QWEN_AUDIO_LANGUAGE", "auto")
    resolved_timeout = timeout_seconds
    if resolved_timeout is None:
        resolved_timeout = int(os.getenv("ANY2MD_QWEN_AUDIO_TIMEOUT", "3600"))
    resolved_template = command_template or os.getenv("ANY2MD_QWEN_AUDIO_COMMAND_TEMPLATE")
    resolved_device_map = device_map or os.getenv("ANY2MD_QWEN_AUDIO_DEVICE_MAP", "cpu")
    resolved_dtype = dtype or os.getenv("ANY2MD_QWEN_AUDIO_DTYPE", "float32")
    resolved_max_new_tokens = max_new_tokens
    if resolved_max_new_tokens is None:
        resolved_max_new_tokens = int(os.getenv("ANY2MD_QWEN_AUDIO_MAX_NEW_TOKENS", "256"))
    resolved_max_inference_batch_size = max_inference_batch_size
    if resolved_max_inference_batch_size is None:
        resolved_max_inference_batch_size = int(os.getenv("ANY2MD_QWEN_AUDIO_MAX_BATCH_SIZE", "1"))

    if resolved_runtime not in {"qwen-asr", "chatllm.cpp", "llama.cpp"}:
        raise MediaProcessingError(
            f"Unsupported local Qwen runtime: {resolved_runtime}. Expected qwen-asr, chatllm.cpp, or llama.cpp."
        )

    missing: list[str] = []
    if not resolved_model:
        missing.append("ANY2MD_QWEN_AUDIO_MODEL")
    if resolved_runtime in {"chatllm.cpp", "llama.cpp"} and not resolved_executable:
        missing.append("ANY2MD_QWEN_AUDIO_EXECUTABLE")
    if missing:
        joined = ", ".join(missing)
        raise MediaProcessingError(
            "Local Qwen3-ASR is not configured. Set the following variables in .env or pass CLI args: "
            f"{joined}"
        )

    model_path = Path(resolved_model)
    if resolved_runtime == "qwen-asr" and model_path.suffix.lower() == ".gguf":
        raise MediaProcessingError(
            "qwen-asr runtime does not use GGUF model files. "
            "Set ANY2MD_QWEN_AUDIO_MODEL to an official Hugging Face model ID like Qwen/Qwen3-ASR-1.7B, "
            "or to a local pretrained model directory."
        )

    if resolved_runtime == "chatllm.cpp" and model_path.suffix.lower() == ".gguf":
        raise MediaProcessingError(
            "chatllm.cpp does not support GGUF model files. "
            "Your current model is GGUF. Use llama.cpp instead, or switch to a chatllm.cpp model file such as .bin."
        )

    return LocalQwenAudioSettings(
        runtime=resolved_runtime,
        model=resolved_model,
        executable=Path(resolved_executable) if resolved_executable else None,
        prompt=resolved_prompt,
        language=resolved_language,
        timeout_seconds=resolved_timeout,
        command_template=resolved_template,
        device_map=resolved_device_map,
        dtype=resolved_dtype,
        max_new_tokens=resolved_max_new_tokens,
        max_inference_batch_size=resolved_max_inference_batch_size,
    )


class LocalQwenAudioConverter:
    AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}

    def __init__(
        self,
        settings: LocalQwenAudioSettings | None = None,
        *,
        env_path: Path | None = None,
        command_runner=None,
        downloader=None,
    ) -> None:
        self._settings = settings
        self._env_path = env_path
        self._command_runner = command_runner or self._run_command
        self._downloader = downloader or self._download_remote_audio

    def __call__(self, path: Path | str) -> str:
        settings = self._settings or resolve_local_qwen_audio_settings(env_path=self._env_path)
        with self._resolve_audio_path(path) as audio_path:
            self._ensure_supported_audio(audio_path)
            command = self._build_command(settings, audio_path)
            result = self._command_runner(command, settings.timeout_seconds)
            transcript = _strip_ansi(result.stdout).strip()
            if transcript:
                return transcript

            stderr = _strip_ansi(result.stderr).strip()
            raise MediaProcessingError(
                "Local Qwen3-ASR produced empty output."
                + (f" stderr: {stderr}" if stderr else "")
            )

    @contextmanager
    def _resolve_audio_path(self, path: Path | str):
        if isinstance(path, str) and AudioConverter._is_remote_url(path):
            with self._downloader(path) as downloaded:
                yield downloaded
            return

        local_path = path if isinstance(path, Path) else Path(path)
        if not local_path.exists():
            raise MediaProcessingError(f"Audio file does not exist: {local_path}")
        yield local_path

    def _build_command(self, settings: LocalQwenAudioSettings, audio_path: Path) -> list[str]:
        if settings.command_template:
            rendered = settings.command_template.format(
                executable=settings.executable,
                model=settings.model,
                audio=audio_path,
                prompt=settings.prompt,
                language=settings.language,
            )
            return [_strip_wrapping_quotes(part) for part in shlex.split(rendered, posix=os.name != "nt")]

        if settings.runtime == "chatllm.cpp":
            return [
                str(settings.executable),
                "-m",
                str(settings.model),
                "--multimedia_file_tags",
                "{{",
                "}}",
                "--set",
                "language",
                settings.language,
                "-p",
                f"{{{{audio:{audio_path}}}}}{settings.prompt}",
            ]

        if settings.runtime == "llama.cpp":
            prompt = settings.prompt
            if settings.language and settings.language != "auto":
                prompt = f"Language: {settings.language}\n{prompt}"
            return [
                str(settings.executable),
                "-m",
                str(settings.model),
                "--audio",
                str(audio_path),
                "--simple-io",
                "-p",
                prompt,
            ]

        raise MediaProcessingError(f"Unsupported local Qwen runtime: {settings.runtime}")

    @staticmethod
    def _run_command(command: list[str], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise MediaProcessingError(f"Local ASR executable was not found: {command[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise MediaProcessingError(
                f"Local Qwen3-ASR timed out after {timeout_seconds}s."
            ) from exc

        if completed.returncode != 0:
            stderr = _strip_ansi(completed.stderr).strip()
            stdout = _strip_ansi(completed.stdout).strip()
            detail = stderr or stdout or f"exit code {completed.returncode}"
            raise MediaProcessingError(f"Local Qwen3-ASR failed: {detail}")
        return completed

    @staticmethod
    @contextmanager
    def _download_remote_audio(url: str):
        parsed = urlparse(url)
        suffix = Path(unquote(parsed.path)).suffix.lower() or ".audio"
        with tempfile.TemporaryDirectory(prefix="any2md-qwen-audio-") as tmp:
            target = Path(tmp) / f"remote{suffix}"
            try:
                with httpx.stream("GET", url, follow_redirects=True, timeout=60.0) as response:
                    response.raise_for_status()
                    with target.open("wb") as file:
                        for chunk in response.iter_bytes():
                            if chunk:
                                file.write(chunk)
            except httpx.HTTPError as exc:
                raise MediaProcessingError(f"Failed to download remote audio: {url}") from exc
            yield target

    def _ensure_supported_audio(self, path: Path) -> None:
        suffix = path.suffix.lower()
        if suffix not in self.AUDIO_SUFFIXES:
            raise MediaProcessingError(f"Unsupported media format: {suffix or '<no suffix>'}")


class QwenAsrAudioConverter:
    AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}

    def __init__(
        self,
        settings: LocalQwenAudioSettings | None = None,
        *,
        env_path: Path | None = None,
        model_loader=None,
    ) -> None:
        self._settings = settings
        self._env_path = env_path
        self._model_loader = model_loader or self._load_model
        self._model = None

    def __call__(self, path: Path | str) -> str:
        settings = self._settings or resolve_local_qwen_audio_settings(env_path=self._env_path)
        audio_input = self._normalize_audio_input(path)
        model = self._model or self._model_loader(settings)
        self._model = model

        try:
            results = model.transcribe(
                audio=audio_input,
                language=_normalize_qwen_asr_language(settings.language),
            )
        except Exception as exc:
            raise MediaProcessingError(f"Local Qwen3-ASR failed: {exc}") from exc

        transcript = _extract_qwen_asr_text(results)
        if not transcript:
            raise MediaProcessingError("Local Qwen3-ASR produced empty output.")
        return transcript

    @classmethod
    def _normalize_audio_input(cls, path: Path | str) -> str:
        if isinstance(path, str) and AudioConverter._is_remote_url(path):
            cls._ensure_supported_suffix(Path(unquote(urlparse(path).path)).suffix.lower())
            return path

        local_path = path if isinstance(path, Path) else Path(path)
        if not local_path.exists():
            raise MediaProcessingError(f"Audio file does not exist: {local_path}")
        cls._ensure_supported_suffix(local_path.suffix.lower())
        return str(local_path)

    @classmethod
    def _ensure_supported_suffix(cls, suffix: str) -> None:
        if suffix not in cls.AUDIO_SUFFIXES:
            raise MediaProcessingError(f"Unsupported media format: {suffix or '<no suffix>'}")

    @staticmethod
    def _load_model(settings: LocalQwenAudioSettings):
        _configure_qwen_asr_runtime_noise()
        try:
            from qwen_asr import Qwen3ASRModel
        except ImportError as exc:
            raise MediaProcessingError(
                "qwen-asr is not installed. Install it with: uv pip install -U qwen-asr"
            ) from exc

        try:
            return Qwen3ASRModel.from_pretrained(
                settings.model,
                dtype=settings.dtype,
                device_map=settings.device_map,
                max_new_tokens=settings.max_new_tokens,
                max_inference_batch_size=settings.max_inference_batch_size,
            )
        except Exception as exc:
            raise MediaProcessingError(f"Failed to initialize qwen-asr model: {exc}") from exc


class AudioConverter:
    AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}

    def __init__(
        self,
        client: AucClient | None = None,
        renderer: AucMarkdownRenderer | None = None,
        task_store: AucTaskStore | None = None,
        wait_for_completion: bool = True,
        progress_callback=None,
    ) -> None:
        self._client = client
        self._renderer = renderer or AucMarkdownRenderer()
        self._task_store = task_store or AucTaskStore()
        self._wait_for_completion = wait_for_completion
        self._progress_callback = progress_callback

    def __call__(self, path: Path | str) -> str:
        if isinstance(path, str) and self._is_remote_url(path):
            return self._convert_from_url(path)

        local_path = path if isinstance(path, Path) else Path(path)
        raise MediaProcessingError(
            f"Local audio files are no longer supported: {local_path}. Provide a direct audio URL instead."
        )

    def _convert_from_url(self, url: str) -> str:
        if self._client is None:
            try:
                settings = load_auc_settings()
                self._client = AucClient(settings)
            except AucNotConfiguredError as exc:
                raise AucNotConfiguredError(
                    "AUC client not configured. Set ANY2MD_AUC_APP_ID and ANY2MD_AUC_ACCESS_KEY in .env"
                ) from exc

        remote_path = self._remote_path(url)
        suffix = remote_path.suffix.lower()
        if suffix not in self.AUDIO_SUFFIXES:
            raise MediaProcessingError(f"Unsupported media format: {suffix or '<no suffix>'}")

        task = self._client.submit(url)
        self._task_store.save(task, url)

        if not self._wait_for_completion:
            raise AudioTaskPendingError(
                task=task,
                audio_url=url,
                reason="Audio task submitted and still processing.",
            )

        transcript = self._poll_task(task, url)
        return self._renderer.render(transcript)

    def _poll_task(self, task: AucTask, audio_url: str):
        import time

        start_time = time.time()
        last_reported_second = -1

        while True:
            elapsed = int(time.time() - start_time)
            if self._progress_callback is not None and elapsed // 10 != last_reported_second // 10:
                self._progress_callback(task, audio_url, elapsed)
                last_reported_second = elapsed

            if elapsed > self._client._settings.max_wait_seconds:
                raise AudioTaskPendingError(
                    task=task,
                    audio_url=audio_url,
                    reason=(
                        f"Audio task is still processing after {self._client._settings.max_wait_seconds}s. "
                        "Use --auc-status to continue checking later."
                    ),
                )

            status = self._client.query(task)
            if status.state == "completed" and status.transcript is not None:
                return status.transcript

            time.sleep(self._client._settings.poll_interval)

    @staticmethod
    def _is_remote_url(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _remote_path(url: str) -> Path:
        parsed = urlparse(url)
        filename = Path(unquote(parsed.path)).name or parsed.netloc or "remote-media"
        return Path(filename)


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)


def _strip_wrapping_quotes(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1]
    return text


def _normalize_qwen_asr_language(language: str | None) -> str | None:
    if language is None:
        return None

    normalized = language.strip().lower()
    if not normalized or normalized == "auto":
        return None
    if normalized in {"zh", "zh-cn", "chinese", "中文", "汉语"}:
        return "Chinese"
    if normalized in {"en", "english", "英语"}:
        return "English"
    return language


def _extract_qwen_asr_text(results) -> str:
    if results is None:
        return ""

    if isinstance(results, str):
        return results.strip()

    if hasattr(results, "text"):
        return str(results.text).strip()

    if isinstance(results, list):
        parts: list[str] = []
        for item in results:
            if isinstance(item, str):
                text = item.strip()
            elif hasattr(item, "text"):
                text = str(item.text).strip()
            elif isinstance(item, dict):
                text = str(item.get("text", "")).strip()
            else:
                text = ""
            if text:
                parts.append(text)
        return "\n".join(parts).strip()

    if isinstance(results, dict):
        return str(results.get("text", "")).strip()

    return ""


def _configure_qwen_asr_runtime_noise() -> None:
    warnings.filterwarnings(
        "ignore",
        category=SyntaxWarning,
        module=r"nagisa\.tagger",
    )

    if os.getenv("TRANSFORMERS_VERBOSITY"):
        return

    try:
        from transformers.utils import logging as transformers_logging
    except Exception:
        return

    transformers_logging.set_verbosity_error()
