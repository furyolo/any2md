from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

from any2md.auc import AucClient, AucMarkdownRenderer
from any2md.auc.client import AucTask
from any2md.auc.errors import AucNotConfiguredError
from any2md.auc.settings import load_auc_settings
from any2md.auc.task_store import AucTaskStore
from any2md.errors import Any2MDError


class MediaProcessingError(Any2MDError):
    """音频处理失败。"""


class AudioTaskPendingError(Any2MDError):
    def __init__(self, task: AucTask, audio_url: str, reason: str) -> None:
        self.task = task
        self.audio_url = audio_url
        self.reason = reason
        super().__init__(reason)


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
