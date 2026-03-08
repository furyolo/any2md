from pathlib import Path
from typing import Protocol


class OcrEngine(Protocol):
    def extract_text(self, path: Path) -> str: ...
