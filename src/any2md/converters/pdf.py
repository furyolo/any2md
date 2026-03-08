from pathlib import Path

import pymupdf4llm


def pdf_to_markdown(path: Path) -> str:
    return pymupdf4llm.to_markdown(str(path))
