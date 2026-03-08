from pathlib import Path

from markdownify import markdownify


def docx_to_markdown(path: Path) -> str:
    import mammoth

    with path.open("rb") as handle:
        result = mammoth.convert_to_html(handle)
    return markdownify(result.value, heading_style="ATX").strip()
