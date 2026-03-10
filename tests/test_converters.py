import sys
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import subprocess

import tests._bootstrap
from any2md.converters.docx import docx_to_markdown
from any2md.converters.epub import epub_to_markdown
from any2md.converters.html import html_to_markdown
from any2md.converters.image import ImageConverter
from any2md.converters.pdf import pdf_to_markdown
from any2md.converters.audio import AudioConverter
from any2md.converters.audio import LocalQwenAudioConverter, LocalQwenAudioSettings
from any2md.converters.audio import QwenAsrAudioConverter
from any2md.converters.audio import _configure_qwen_asr_runtime_noise
from any2md.converters.audio import resolve_local_qwen_audio_settings
from any2md.io_state import resume_state_path
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

    def test_local_qwen_audio_converter_transcribes_local_file(self) -> None:
        executed: list[list[str]] = []

        def fake_runner(command: list[str], _timeout: int) -> subprocess.CompletedProcess[str]:
            executed.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="transcribed\n", stderr="")

        settings = LocalQwenAudioSettings(
            runtime="chatllm.cpp",
            executable=Path("chatllm.exe"),
            model=Path("qwen3-asr.gguf"),
            language="zh",
        )
        converter = LocalQwenAudioConverter(settings=settings, command_runner=fake_runner)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo.mp3"
            path.write_bytes(b"fake-audio")
            result = converter(path)

        self.assertEqual(result, "transcribed")
        self.assertEqual(executed[0][0], "chatllm.exe")
        self.assertIn("--multimedia_file_tags", executed[0])
        self.assertTrue(any("{{audio:" in part for part in executed[0]))

    def test_local_qwen_audio_converter_uses_custom_template_for_llama_cpp(self) -> None:
        executed: list[list[str]] = []

        def fake_runner(command: list[str], _timeout: int) -> subprocess.CompletedProcess[str]:
            executed.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="llama-transcribed", stderr="")

        settings = LocalQwenAudioSettings(
            runtime="llama.cpp",
            executable=Path("llama-cli.exe"),
            model=Path("qwen3-asr.gguf"),
            command_template='"{executable}" -m "{model}" --audio "{audio}" --prompt "{prompt}"',
        )
        converter = LocalQwenAudioConverter(settings=settings, command_runner=fake_runner)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo.wav"
            path.write_bytes(b"fake-audio")
            result = converter(path)

        self.assertEqual(result, "llama-transcribed")
        self.assertEqual(executed[0][0], "llama-cli.exe")
        self.assertIn("--audio", executed[0])

    def test_local_qwen_audio_converter_builds_default_llama_cpp_command(self) -> None:
        executed: list[list[str]] = []

        def fake_runner(command: list[str], _timeout: int) -> subprocess.CompletedProcess[str]:
            executed.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="llama-default", stderr="")

        settings = LocalQwenAudioSettings(
            runtime="llama.cpp",
            executable=Path("llama-cli.exe"),
            model=Path("qwen3-asr.gguf"),
            language="zh",
        )
        converter = LocalQwenAudioConverter(settings=settings, command_runner=fake_runner)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo.wav"
            path.write_bytes(b"fake-audio")
            result = converter(path)

        self.assertEqual(result, "llama-default")
        self.assertEqual(executed[0][0], "llama-cli.exe")
        self.assertIn("--audio", executed[0])
        self.assertIn("--simple-io", executed[0])
        self.assertTrue(any(part.startswith("Language: zh") for part in executed[0]))

    def test_local_qwen_settings_reject_chatllm_cpp_with_gguf_model(self) -> None:
        with self.assertRaises(MediaProcessingError) as context:
            resolve_local_qwen_audio_settings(
                runtime="chatllm.cpp",
                executable="D:/Coding/models/chatllm_win_x64/bin/main.exe",
                model="D:/Coding/models/qwen3-asr-1.7b-GGUF/qwen3-asr-1.7b-q8_0.gguf",
            )

        self.assertIn("does not support GGUF model files", str(context.exception))
        self.assertIn("Use llama.cpp instead", str(context.exception))

    def test_local_qwen_settings_reject_qwen_asr_with_gguf_model(self) -> None:
        with self.assertRaises(MediaProcessingError) as context:
            resolve_local_qwen_audio_settings(
                runtime="qwen-asr",
                model="D:/Coding/models/qwen3-asr-1.7b-GGUF/qwen3-asr-1.7b-q8_0.gguf",
            )

        self.assertIn("does not use GGUF model files", str(context.exception))

    def test_qwen_asr_audio_converter_transcribes_with_official_backend(self) -> None:
        class FakeResult:
            def __init__(self, text: str) -> None:
                self.text = text

        class FakeModel:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str | None]] = []

            def transcribe(self, *, audio: str, language: str | None):
                self.calls.append((audio, language))
                return [FakeResult("第一句"), FakeResult("第二句")]

        fake_model = FakeModel()
        settings = LocalQwenAudioSettings(
            runtime="qwen-asr",
            model="Qwen/Qwen3-ASR-1.7B",
            language="zh",
        )
        converter = QwenAsrAudioConverter(
            settings=settings,
            model_loader=lambda _settings: fake_model,
            duration_probe=lambda _path: 1,
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo.mp3"
            path.write_bytes(b"fake-audio")
            result = converter(path)

        self.assertEqual(result, "第一句\n第二句")
        self.assertEqual(fake_model.calls[0][1], "Chinese")

    def test_qwen_asr_audio_converter_can_resume_from_checkpoint(self) -> None:
        class FakeResult:
            def __init__(self, text: str) -> None:
                self.text = text

        class FakeModel:
            def __init__(self) -> None:
                self.calls: list[str] = []
                self.second_chunk_attempts = 0

            def transcribe(self, *, audio: str, language: str | None):
                name = Path(audio).name
                self.calls.append(name)
                if name.startswith("chunk_000"):
                    return [FakeResult("第一段")]
                if name.startswith("chunk_001"):
                    self.second_chunk_attempts += 1
                    if self.second_chunk_attempts <= 3:
                        raise RuntimeError("第二段失败")
                    return [FakeResult("第二段")]
                raise AssertionError(f"unexpected chunk: {name}")

        def fake_splitter(_source: Path, _chunk_duration: int, _total_duration: float, output_dir: Path) -> list[Path]:
            first = output_dir / "chunk_000.mp3"
            second = output_dir / "chunk_001.mp3"
            first.write_bytes(b"chunk-1")
            second.write_bytes(b"chunk-2")
            return [first, second]

        fake_model = FakeModel()
        settings = LocalQwenAudioSettings(
            runtime="qwen-asr",
            model="Qwen/Qwen3-ASR-1.7B",
            language="zh",
            chunk_duration_seconds=10,
        )
        converter = QwenAsrAudioConverter(
            settings=settings,
            model_loader=lambda _settings: fake_model,
            duration_probe=lambda _path: 30,
            audio_splitter=fake_splitter,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "demo.mp3"
            output = root / "demo.md"
            source.write_bytes(b"fake-audio")

            with self.assertRaises(MediaProcessingError) as context:
                converter(source, output_path=output)

            self.assertIn("已保留续传进度", str(context.exception))
            self.assertTrue(output.exists())
            self.assertEqual(output.read_text(encoding="utf-8"), "第一段\n")
            self.assertTrue(resume_state_path(output).exists())

            resumed = converter(source, output_path=output)

            self.assertEqual(resumed, "第一段\n第二段")
            self.assertEqual(output.read_text(encoding="utf-8"), "第一段\n第二段")
            self.assertFalse(resume_state_path(output).exists())
            self.assertEqual(fake_model.calls.count("chunk_000.mp3"), 1)
            self.assertGreaterEqual(fake_model.calls.count("chunk_001.mp3"), 4)

    @patch("transformers.utils.logging.set_verbosity_error")
    def test_qwen_asr_runtime_noise_defaults_to_quiet_transformers(self, mocked_set_verbosity_error) -> None:
        with patch.dict(os.environ, {}, clear=True):
            _configure_qwen_asr_runtime_noise()

        mocked_set_verbosity_error.assert_called_once()




