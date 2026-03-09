import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import tests._bootstrap
from any2md.converters.docx import docx_to_markdown
from any2md.converters.epub import epub_to_markdown
from any2md.converters.html import html_to_markdown
from any2md.converters.image import ImageConverter
from any2md.converters.pdf import pdf_to_markdown
from any2md.converters.audio import AudioConverter
from any2md.converters.text import text_to_markdown
from any2md.errors import OcrNotConfiguredError
from any2md.converters.audio import MediaProcessingError


class FakeEpubItem:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def get_content(self) -> bytes:
        return self._content


class FakeEpubBook:
    def __init__(self, items) -> None:
        self._items = items

    def get_items_of_type(self, _):
        return self._items


class FakeHtmlResult:
    def __init__(self, value: str) -> None:
        self.value = value


class FakeOcrEngine:
    def extract_text(self, path: Path) -> str:
        return f"  extracted:{path.name}  "


class FakeTranscript:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeAucClient:
    def __init__(self) -> None:
        self.audio_url = None

    def transcribe(self, audio_url):
        self.audio_url = audio_url
        return FakeTranscript("transcribed")


class FakeRenderer:
    def render(self, transcript) -> str:
        return transcript.text


class ConverterTests(unittest.TestCase):
    @patch("any2md.converters.pdf.pymupdf4llm.to_markdown", return_value="pdf-markdown")
    def test_pdf_converter_delegates_to_pymupdf4llm(self, mocked) -> None:
        path = Path("sample.pdf")
        self.assertEqual(pdf_to_markdown(path), "pdf-markdown")
        mocked.assert_called_once_with(str(path))

    @patch("any2md.converters.epub.markdownify", side_effect=["# Title", "", "## Section"])
    @patch("any2md.converters.epub.epub.read_epub")
    def test_epub_converter_preserves_existing_semantics(self, mocked_read_epub, mocked_markdownify) -> None:
        mocked_read_epub.return_value = FakeEpubBook(
            [
                FakeEpubItem(b'<?xml version="1.0"?><h1>Title</h1>'),
                FakeEpubItem(b"<p></p>"),
                FakeEpubItem(b"<h2>Section</h2>"),
            ]
        )

        result = epub_to_markdown(Path("sample.epub"))

        self.assertEqual(result, "# Title\n\n---\n\n## Section")
        self.assertNotIn("<?xml", mocked_markdownify.call_args_list[0].args[0])

    @patch("any2md.converters.html.markdownify", return_value="# Hello")
    def test_html_converter_uses_markdownify(self, mocked_markdownify) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "page.html"
            path.write_text("<h1>Hello</h1>", encoding="utf-8")
            self.assertEqual(html_to_markdown(path), "# Hello")
            mocked_markdownify.assert_called_once()

    def test_text_converter_returns_utf8_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "note.txt"
            path.write_text("plain text", encoding="utf-8")
            result = text_to_markdown(path)
            self.assertEqual(result, "plain text")
            self.assertEqual(result.source_encoding, "utf-8")

    def test_text_converter_supports_utf16_with_bom(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "note.txt"
            path.write_text("|鈥斺€?鏍囬", encoding="utf-16")
            result = text_to_markdown(path)
            self.assertEqual(result, "|鈥斺€?鏍囬")
            self.assertEqual(result.source_encoding, "utf-16")

    def test_text_converter_falls_back_to_gb18030_without_bom(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "note.txt"
            path.write_bytes("|鈥斺€?鏍囬".encode("gb18030"))
            result = text_to_markdown(path)
            self.assertEqual(result, "|鈥斺€?鏍囬")
            self.assertEqual(result.source_encoding, "gb18030")

    def test_text_converter_reports_attempted_encodings_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "note.txt"
            path.write_bytes(b"\x81")
            with self.assertRaises(UnicodeDecodeError) as context:
                text_to_markdown(path)
            self.assertIn("attempted encodings: utf-8, gb18030", str(context.exception))

    @patch("any2md.converters.docx.markdownify", return_value="# Docx")
    def test_docx_converter_uses_html_bridge(self, mocked_markdownify) -> None:
        fake_mammoth = types.SimpleNamespace(
            convert_to_html=Mock(return_value=FakeHtmlResult("<h1>Docx</h1>"))
        )
        sentinel = object()
        previous = sys.modules.get("mammoth", sentinel)
        sys.modules["mammoth"] = fake_mammoth
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "sample.docx"
                path.write_bytes(b"docx")
                self.assertEqual(docx_to_markdown(path), "# Docx")
                fake_mammoth.convert_to_html.assert_called_once()
                mocked_markdownify.assert_called_once_with("<h1>Docx</h1>", heading_style="ATX")
        finally:
            if previous is sentinel:
                sys.modules.pop("mammoth", None)
            else:
                sys.modules["mammoth"] = previous

    def test_image_converter_requires_engine(self) -> None:
        with self.assertRaises(OcrNotConfiguredError):
            ImageConverter()(Path("image.png"))

    def test_image_converter_uses_engine(self) -> None:
        converter = ImageConverter(FakeOcrEngine())
        self.assertEqual(converter(Path("image.png")), "extracted:image.png")

    def test_image_converter_cleans_ocr_wrapper_text(self) -> None:
        class WrappedOcrEngine:
            def extract_text(self, path: Path) -> str:
                return "here is the ocr markdown:\n\n#Title\n-Item"

        converter = ImageConverter(WrappedOcrEngine())
        self.assertEqual(converter(Path("image.png")), "# Title\n- Item")

    def test_audio_converter_rejects_remote_video_url(self) -> None:
        client = FakeAucClient()
        converter = AudioConverter(client=client, renderer=FakeRenderer())

        with self.assertRaises(MediaProcessingError) as context:
            converter("https://example.com/media/demo.mp4?token=1")

        self.assertIn("Unsupported media format: .mp4", str(context.exception))

    def test_audio_converter_rejects_local_audio_file(self) -> None:
        client = FakeAucClient()
        converter = AudioConverter(client=client, renderer=FakeRenderer())

        with self.assertRaises(MediaProcessingError) as context:
            converter(Path("demo.mp3"))

        self.assertIn("Local audio files are no longer supported", str(context.exception))




