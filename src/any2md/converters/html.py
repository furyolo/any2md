from pathlib import Path

from markdownify import markdownify


def html_to_markdown(path: Path) -> str:
    html = path.read_text(encoding="utf-8")
    return markdownify(html, heading_style="ATX").strip()
