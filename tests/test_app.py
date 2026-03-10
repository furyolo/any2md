import os
import tempfile
import unittest
from pathlib import Path

import tests._bootstrap
from any2md.app import ConversionService
from any2md.registry import ConverterRegistry


def ok_converter(path: Path) -> str:
    return f"converted:{path.name}"


def bad_converter(path: Path) -> str:
    raise RuntimeError("boom")


def unexpected_converter_call(path: Path) -> str:
    raise AssertionError("converter should not be called")


class AppTests(unittest.TestCase):
    def test_remote_audio_url_can_be_passed_directly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "audio.md"
            received: list[str] = []

            def remote_converter(path: str) -> str:
                received.append(path)
                return "remote-ok"

            registry = ConverterRegistry()
            registry.register([".mp3"], remote_converter)

            summary = ConversionService(registry=registry).run(
                inputs=["https://example.com/audio.mp3"],
                output_path=str(target),
            )

            self.assertEqual(summary.converted_count, 1)
            self.assertEqual(summary.failure_count, 0)
            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(encoding="utf-8"), "remote-ok")
            self.assertEqual(received, ["https://example.com/audio.mp3"])

    def test_local_audio_file_is_reported_as_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "audio.mp3"
            source.write_bytes(b"fake-audio")

            summary = ConversionService(registry=ConverterRegistry()).run(
                inputs=[str(source)],
                output_path=str(root / "audio.md"),
            )

            self.assertEqual(summary.converted_count, 0)
            self.assertEqual(summary.skipped_count, 1)
            self.assertEqual(summary.exit_code, 1)
            self.assertIn(
                "Local audio files are no longer supported",
                summary.results[0].message or "",
            )

    def test_local_audio_file_can_be_processed_when_backend_allows_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "audio.mp3"
            target = root / "audio.md"
            source.write_bytes(b"fake-audio")
            received: list[Path] = []

            def local_audio_converter(path: Path) -> str:
                received.append(path)
                return "local-audio-ok"

            registry = ConverterRegistry()
            registry.register([".mp3"], local_audio_converter)

            summary = ConversionService(
                registry=registry,
                allow_local_audio_inputs=True,
            ).run(
                inputs=[str(source)],
                output_path=str(target),
            )

            self.assertEqual(summary.converted_count, 1)
            self.assertEqual(summary.failure_count, 0)
            self.assertEqual(received, [source.resolve()])
            self.assertEqual(target.read_text(encoding="utf-8"), "local-audio-ok")

    def test_remote_video_url_is_reported_as_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "output"

            summary = ConversionService(registry=ConverterRegistry()).run(
                inputs=["https://example.com/media/video.mp4?token=abc"],
                output_path=str(output_dir) + os.sep,
            )

            self.assertEqual(summary.converted_count, 0)
            self.assertEqual(summary.skipped_count, 1)
            self.assertEqual(summary.exit_code, 1)
            self.assertFalse((output_dir / "video.md").exists())
            self.assertIn("Unsupported format: .mp4", summary.results[0].message or "")

    def test_batch_isolates_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "inputs"
            output_dir = root / "output"
            source_dir.mkdir()
            (source_dir / "good.ok").write_text("good", encoding="utf-8")
            (source_dir / "bad.bad").write_text("bad", encoding="utf-8")

            registry = ConverterRegistry()
            registry.register([".ok"], ok_converter)
            registry.register([".bad"], bad_converter)

            summary = ConversionService(registry=registry).run(
                inputs=[str(source_dir)],
                output_path=str(output_dir),
            )

            self.assertEqual(summary.converted_count, 1)
            self.assertEqual(summary.failure_count, 1)
            self.assertEqual(summary.skipped_count, 0)
            self.assertEqual(summary.exit_code, 2)
            self.assertTrue((output_dir / "good.md").exists())
            self.assertFalse((output_dir / "bad.md").exists())

    def test_batch_output_collision_isolated_per_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_dir = root / "first"
            second_dir = root / "second"
            first_dir.mkdir()
            second_dir.mkdir()
            first = first_dir / "same.ok"
            second = second_dir / "same.ok"
            first.write_text("one", encoding="utf-8")
            second.write_text("two", encoding="utf-8")

            registry = ConverterRegistry()
            registry.register([".ok"], ok_converter)

            summary = ConversionService(registry=registry).run(
                inputs=[str(first), str(second)],
                output_path=str(root / "out"),
            )

            self.assertEqual(summary.converted_count, 0)
            self.assertEqual(summary.failure_count, 2)
            self.assertTrue(all(result.error for result in summary.results if result.failed))

    def test_directory_scan_reports_unsupported_files_as_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "inputs"
            output_dir = root / "output"
            source_dir.mkdir()
            (source_dir / "good.ok").write_text("good", encoding="utf-8")
            (source_dir / "ignored.bin").write_text("ignored", encoding="utf-8")

            registry = ConverterRegistry()
            registry.register([".ok"], ok_converter)

            summary = ConversionService(registry=registry).run(
                inputs=[str(source_dir)],
                output_path=str(output_dir),
            )

            self.assertEqual(summary.converted_count, 1)
            self.assertEqual(summary.skipped_count, 1)
            self.assertEqual(summary.failure_count, 0)
            self.assertEqual(summary.exit_code, 0)
            self.assertTrue((output_dir / "good.md").exists())
            skipped = [result for result in summary.results if result.skipped]
            self.assertEqual(len(skipped), 1)
            self.assertIn("Unsupported format", skipped[0].message or "")

    def test_direct_unsupported_file_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "note.bin"
            source.write_text("data", encoding="utf-8")

            summary = ConversionService(registry=ConverterRegistry()).run(
                inputs=[str(source)],
                output_path=str(root / "out.md"),
            )

            self.assertEqual(summary.converted_count, 0)
            self.assertEqual(summary.skipped_count, 1)
            self.assertEqual(summary.failure_count, 0)
            self.assertEqual(summary.exit_code, 1)
            self.assertTrue(summary.results[0].skipped)

    def test_dry_run_plans_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "note.ok"
            target = root / "result.md"
            source.write_text("content", encoding="utf-8")

            registry = ConverterRegistry()
            registry.register([".ok"], unexpected_converter_call)

            summary = ConversionService(registry=registry).run(
                inputs=[str(source)],
                output_path=str(target),
                dry_run=True,
            )

            self.assertEqual(summary.planned_count, 1)
            self.assertEqual(summary.failure_count, 0)
            self.assertEqual(summary.exit_code, 0)
            self.assertFalse(target.exists())
            self.assertTrue(summary.results[0].planned)

    def test_single_file_accepts_custom_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "note.ok"
            target = root / "custom"
            source.write_text("content", encoding="utf-8")

            registry = ConverterRegistry()
            registry.register([".ok"], ok_converter)

            summary = ConversionService(registry=registry).run(
                inputs=[str(source)],
                output_path=str(target),
            )

            self.assertEqual(summary.exit_code, 0)
            self.assertEqual(summary.converted_count, 1)
            self.assertEqual(target.read_text(encoding="utf-8"), "converted:note.ok")

    def test_single_file_default_output_uses_source_stem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "note.ok"
            target = root / "output" / "note.md"
            source.write_text("content", encoding="utf-8")

            registry = ConverterRegistry()
            registry.register([".ok"], ok_converter)

            original_cwd = Path.cwd()
            os.chdir(root)
            try:
                summary = ConversionService(registry=registry).run(inputs=[str(source)])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(summary.exit_code, 0)
            self.assertEqual(summary.converted_count, 1)
            self.assertEqual(target.read_text(encoding="utf-8"), "converted:note.ok")

    def test_force_controls_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "note.ok"
            target = root / "custom.md"
            source.write_text("content", encoding="utf-8")
            target.write_text("old", encoding="utf-8")

            registry = ConverterRegistry()
            registry.register([".ok"], ok_converter)

            without_force = ConversionService(registry=registry).run(
                inputs=[str(source)],
                output_path=str(target),
            )
            self.assertEqual(without_force.converted_count, 0)
            self.assertEqual(without_force.failure_count, 1)
            self.assertIn("Use --force", without_force.results[0].error or "")

            with_force = ConversionService(registry=registry).run(
                inputs=[str(source)],
                output_path=str(target),
                force=True,
            )
            self.assertEqual(with_force.converted_count, 1)
            self.assertEqual(target.read_text(encoding="utf-8"), "converted:note.ok")
