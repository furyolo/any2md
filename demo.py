import sys
import pathlib
import pymupdf4llm
import ebooklib
from ebooklib import epub
from markdownify import markdownify


def pdf_to_markdown(path: str) -> str:
    return pymupdf4llm.to_markdown(path)


def epub_to_markdown(path: str) -> str:
    import re
    book = epub.read_epub(path)
    parts = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        html = item.get_content().decode("utf-8")
        html = re.sub(r"<\?xml[^?]*\?>", "", html)
        md = markdownify(html, heading_style="ATX").strip()
        if md:
            parts.append(md)
    return "\n\n---\n\n".join(parts)


_CONVERTERS = {
    ".pdf": pdf_to_markdown,
    ".epub": epub_to_markdown,
}


def convert(input_path: str, output_path: str = "output.md", t2s: bool = False) -> None:
    ext = pathlib.Path(input_path).suffix.lower()
    converter = _CONVERTERS.get(ext)
    if converter is None:
        raise ValueError(f"Unsupported format: {ext}")
    md_text = converter(input_path)
    if t2s:
        import opencc
        md_text = opencc.OpenCC("t2s").convert(md_text)
    pathlib.Path(output_path).write_bytes(md_text.encode())
    print(f"Saved to {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python demo.py <input.pdf|input.epub> [--t2s]")
        sys.exit(1)
    convert(sys.argv[1], t2s="--t2s" in sys.argv)
