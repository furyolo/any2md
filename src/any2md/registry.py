from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from any2md.converters.audio import AudioConverter
from any2md.converters.docx import docx_to_markdown
from any2md.converters.epub import epub_to_markdown
from any2md.converters.html import html_to_markdown
from any2md.converters.image import ImageConverter
from any2md.converters.pdf import pdf_to_markdown
from any2md.converters.text import text_to_markdown
from any2md.errors import UnsupportedFormatError
from any2md.ocr import OcrEngine, build_default_ocr_engine

ConverterInput = Path | str
Converter = Callable[[ConverterInput], str]


class ConverterRegistry:
    def __init__(self) -> None:
        self._converters: dict[str, Converter] = {}

    def register(self, suffixes: Iterable[str], converter: Converter) -> None:
        for suffix in suffixes:
            normalized = normalize_suffix(suffix)
            if normalized in self._converters:
                raise ValueError(f"Converter already registered for suffix: {normalized}")
            self._converters[normalized] = converter

    def get(self, suffix: str) -> Converter:
        normalized = normalize_suffix(suffix)
        try:
            return self._converters[normalized]
        except KeyError as exc:
            raise UnsupportedFormatError(f"Unsupported format: {normalized}") from exc

    def convert(self, path: ConverterInput, *, suffix: str | None = None) -> str:
        resolved_suffix = suffix
        if resolved_suffix is None:
            resolved_suffix = path.suffix if isinstance(path, Path) else Path(path).suffix
        return self.get(resolved_suffix)(path)

    def supports(self, suffix: str) -> bool:
        if not suffix:
            return False
        return normalize_suffix(suffix) in self._converters

    def suffixes(self) -> tuple[str, ...]:
        return tuple(sorted(self._converters))


def build_default_registry(
    ocr_engine: OcrEngine | None = None,
    audio_converter: AudioConverter | None = None,
) -> ConverterRegistry:
    registry = ConverterRegistry()
    registry.register([".pdf"], pdf_to_markdown)
    registry.register([".epub"], epub_to_markdown)
    registry.register([".html", ".htm"], html_to_markdown)
    registry.register([".txt"], text_to_markdown)
    registry.register([".docx"], docx_to_markdown)
    registry.register([".jpg", ".jpeg", ".png"], ImageConverter(ocr_engine or build_default_ocr_engine()))

    audio_converter = audio_converter or AudioConverter()
    registry.register(
        [".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"],
        audio_converter,
    )

    return registry


def normalize_suffix(suffix: str) -> str:
    if not suffix:
        raise ValueError("Suffix must not be empty")
    if not suffix.startswith("."):
        suffix = f".{suffix}"
    return suffix.lower()
