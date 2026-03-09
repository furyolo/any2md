import os
import tempfile
import unittest
from io import StringIO
from pathlib import Path

import tests._bootstrap
from any2md.cli import main
from any2md.converters.text import text_to_markdown
from any2md.registry import ConverterRegistry


def ok_converter(path: Path) -> str:
    return "ok"


def bad_converter(path: Path) -> str:
    raise RuntimeError("boom")


def unexpected_converter_call(path: Path) -> str:
    raise AssertionError("converter should not be called")


class CliTests(unittest.TestCase):
    def test_cli_returns_partial_failure_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            good = root / "good.ok"
            bad = root / "bad.bad"
            output_dir = root / "out"
            good.write_text("good", encoding="utf-8")
            bad.write_text("bad", encoding="utf-8")

            registry = ConverterRegistry()
            registry.register([".ok"], ok_converter)
            registry.register([".bad"], bad_converter)

            stdout = StringIO()
            stderr = StringIO()
            code = main(
                [str(good), str(bad), "--output", str(output_dir)],
                registry=registry,
                stdout=stdout,
                stderr=stderr,
            )

            self.assertEqual(code, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("Converted", stderr.getvalue())
            self.assertIn("Failed", stderr.getvalue())
            self.assertIn(
                "Summary: total=2 converted=1 planned=0 skipped=0 failed=1",
                stderr.getvalue(),
            )

    def test_cli_single_file_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "note.ok"
            output = root / "note.md"
            source.write_text("data", encoding="utf-8")

            registry = ConverterRegistry()
            registry.register([".ok"], ok_converter)

            stdout = StringIO()
            stderr = StringIO()
            code = main(
                [str(source), "--output", str(output)],
                registry=registry,
                stdout=stdout,
                stderr=stderr,
            )

            self.assertEqual(code, 0)
            self.assertTrue(output.exists())
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("Converted", stderr.getvalue())

    def test_cli_reports_detected_text_encoding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "note.txt"
            output = root / "note.md"
            source.write_bytes("|鈥斺€?鏍囬".encode("gb18030"))

            registry = ConverterRegistry()
            registry.register([".txt"], text_to_markdown)

            stdout = StringIO()
            stderr = StringIO()
            code = main(
                [str(source), "--output", str(output)],
                registry=registry,
                stdout=stdout,
                stderr=stderr,
            )

            self.assertEqual(code, 0)
            self.assertTrue(output.exists())
            self.assertEqual(output.read_text(encoding="utf-8"), "|鈥斺€?鏍囬")
            self.assertIn("encoding=gb18030", stderr.getvalue())

    def test_cli_reports_attempted_encodings_for_text_decode_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "note.txt"
            output = root / "note.md"
            source.write_bytes(b"\x81")

            registry = ConverterRegistry()
            registry.register([".txt"], text_to_markdown)

            stdout = StringIO()
            stderr = StringIO()
            code = main(
                [str(source), "--output", str(output)],
                registry=registry,
                stdout=stdout,
                stderr=stderr,
            )

            self.assertEqual(code, 1)
            self.assertFalse(output.exists())
            self.assertIn("Failed", stderr.getvalue())
            self.assertIn("attempted encodings: utf-8, gb18030", stderr.getvalue())

    def test_cli_single_file_default_output_uses_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "note.ok"
            output = root / "output" / "note.md"
            source.write_text("data", encoding="utf-8")

            registry = ConverterRegistry()
            registry.register([".ok"], ok_converter)

            stdout = StringIO()
            stderr = StringIO()
            original_cwd = Path.cwd()
            os.chdir(root)
            try:
                code = main(
                    [str(source)],
                    registry=registry,
                    stdout=stdout,
                    stderr=stderr,
                )
            finally:
                os.chdir(original_cwd)

            self.assertEqual(code, 0)
            self.assertTrue(output.exists())
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("Converted", stderr.getvalue())

    def test_cli_reports_skipped_files_and_returns_one_when_nothing_converts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "note.bin"
            source.write_text("data", encoding="utf-8")

            stdout = StringIO()
            stderr = StringIO()
            code = main(
                [str(source)],
                registry=ConverterRegistry(),
                stdout=stdout,
                stderr=stderr,
            )

            self.assertEqual(code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("Skipped", stderr.getvalue())
            self.assertIn(
                "Summary: total=1 converted=0 planned=0 skipped=1 failed=0",
                stderr.getvalue(),
            )

    def test_cli_dry_run_does_not_write_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "note.ok"
            output = root / "note.md"
            source.write_text("data", encoding="utf-8")

            registry = ConverterRegistry()
            registry.register([".ok"], unexpected_converter_call)

            stdout = StringIO()
            stderr = StringIO()
            code = main(
                [str(source), "--output", str(output), "--dry-run"],
                registry=registry,
                stdout=stdout,
                stderr=stderr,
            )

            self.assertEqual(code, 0)
            self.assertEqual(stdout.getvalue(), "")
            self.assertFalse(output.exists())
            self.assertIn("Planned", stderr.getvalue())

    def test_cli_force_allows_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "note.ok"
            output = root / "note.md"
            source.write_text("data", encoding="utf-8")
            output.write_text("old", encoding="utf-8")

            registry = ConverterRegistry()
            registry.register([".ok"], ok_converter)

            stdout = StringIO()
            stderr = StringIO()
            without_force = main(
                [str(source), "--output", str(output)],
                registry=registry,
                stdout=stdout,
                stderr=stderr,
            )
            self.assertEqual(without_force, 1)
            self.assertIn("Use --force", stderr.getvalue())

            stdout = StringIO()
            stderr = StringIO()
            with_force = main(
                [str(source), "--output", str(output), "--force"],
                registry=registry,
                stdout=stdout,
                stderr=stderr,
            )
            self.assertEqual(with_force, 0)
            self.assertEqual(output.read_text(encoding="utf-8"), "ok")


