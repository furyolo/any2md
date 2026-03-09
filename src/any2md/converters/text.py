from __future__ import annotations

from codecs import BOM_UTF8, BOM_UTF16_BE, BOM_UTF16_LE, BOM_UTF32_BE, BOM_UTF32_LE
from pathlib import Path


class DecodedText(str):
    def __new__(cls, value: str, *, source_encoding: str):
        instance = super().__new__(cls, value)
        instance.source_encoding = source_encoding
        return instance


def text_to_markdown(path: Path) -> str:
    raw = path.read_bytes()
    text, source_encoding = _decode_text(raw)
    return DecodedText(text, source_encoding=source_encoding)


def _decode_text(raw: bytes) -> tuple[str, str]:
    detected_encoding = _detect_text_encoding(raw)
    if detected_encoding is not None:
        try:
            return raw.decode(detected_encoding), detected_encoding
        except UnicodeDecodeError as exc:
            raise _build_decode_error(exc, attempted_encodings=(detected_encoding,)) from exc
    return _decode_text_without_bom(raw)


def _detect_text_encoding(raw: bytes) -> str | None:
    if raw.startswith(BOM_UTF8):
        return "utf-8-sig"
    if raw.startswith(BOM_UTF32_LE) or raw.startswith(BOM_UTF32_BE):
        return "utf-32"
    if raw.startswith(BOM_UTF16_LE) or raw.startswith(BOM_UTF16_BE):
        return "utf-16"
    return None


def _decode_text_without_bom(raw: bytes) -> tuple[str, str]:
    attempted_encodings = ("utf-8", "gb18030")
    first_error: UnicodeDecodeError | None = None
    for encoding in attempted_encodings:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError as exc:
            if first_error is None:
                first_error = exc
    if first_error is not None:
        raise _build_decode_error(first_error, attempted_encodings=attempted_encodings) from first_error
    raise UnicodeDecodeError("utf-8", raw, 0, 1, "Unable to determine text encoding")


def _build_decode_error(
    error: UnicodeDecodeError,
    *,
    attempted_encodings: tuple[str, ...],
) -> UnicodeDecodeError:
    attempted = ", ".join(attempted_encodings)
    return UnicodeDecodeError(
        error.encoding,
        error.object,
        error.start,
        error.end,
        f"{error.reason}; attempted encodings: {attempted}",
    )


