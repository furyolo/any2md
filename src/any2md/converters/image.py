from pathlib import Path

from any2md.errors import OcrNotConfiguredError
from any2md.ocr import OcrEngine
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
