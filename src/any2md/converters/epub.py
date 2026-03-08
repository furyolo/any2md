import re
from pathlib import Path

import ebooklib
from ebooklib import epub
from markdownify import markdownify


def epub_to_markdown(path: Path) -> str:
    book = epub.read_epub(str(path))
    parts: list[str] = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        html = item.get_content().decode("utf-8")
        html = re.sub(r"<\?xml[^?]*\?>", "", html)
        markdown = markdownify(html, heading_style="ATX").strip()
        if markdown:
            parts.append(markdown)
    return "\n\n---\n\n".join(parts)
