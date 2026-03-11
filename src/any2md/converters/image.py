from pathlib import Path

from any2md.errors import OcrNotConfiguredError
from any2md.ocr import OcrEngine, LlmOcrSettings, ocr_image_async, resolve_llm_ocr_settings
from any2md.postprocess import apply_postprocess


class ImageConverter:
    def __init__(self, engine: OcrEngine | None = None) -> None:
        self._engine = engine

    def __call__(self, path: Path) -> str:
        if self._engine is None:
            raise OcrNotConfiguredError(
                "OCR engine is not configured. Install or inject an OCR engine before converting images."
            )
        return apply_postprocess(
            self._engine.extract_text(path),
            ocr_cleanup=True,
        ).strip()


class ImageAsyncConverter:
    """Async version of ImageConverter using ocr_image_async."""

    def __init__(
        self,
        settings: LlmOcrSettings | None = None,
        *,
        env_path: Path | None = None,
    ) -> None:
        self._settings = settings
        self._env_path = env_path

    async def __call__(self, path: Path) -> str:
        settings = self._settings or resolve_llm_ocr_settings(env_path=self._env_path)
        raw_text = await ocr_image_async(path, settings)
        return apply_postprocess(raw_text, ocr_cleanup=True).strip()
