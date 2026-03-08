import tempfile
import unittest
from pathlib import Path

import tests._bootstrap
from any2md.errors import OutputPathError
from any2md.paths import ensure_no_output_collisions, resolve_output_path


class PathTests(unittest.TestCase):
    def test_single_file_defaults_to_source_stem_md(self) -> None:
        result = resolve_output_path(
            input_path=Path("/tmp/example.pdf"),
            batch_mode=False,
            output_path=None,
            raw_output_path=None,
            source_root=Path("/tmp"),
        )
        self.assertEqual(result, Path("example.md"))

    def test_single_file_directory_output_uses_input_stem(self) -> None:
        result = resolve_output_path(
            input_path=Path("/tmp/example.pdf"),
            batch_mode=False,
            output_path=Path("/tmp/out"),
            raw_output_path="/tmp/out/",
            source_root=Path("/tmp"),
        )
        self.assertEqual(result, Path("/tmp/out/example.md"))

    def test_single_file_plain_output_path_is_treated_as_file(self) -> None:
        result = resolve_output_path(
            input_path=Path("/tmp/example.pdf"),
            batch_mode=False,
            output_path=Path("/tmp/result"),
            raw_output_path="/tmp/result",
            source_root=Path("/tmp"),
        )
        self.assertEqual(result, Path("/tmp/result"))

    def test_batch_mode_uses_relative_directory_layout(self) -> None:
        result = resolve_output_path(
            input_path=Path("/tmp/in/nested/example.epub"),
            batch_mode=True,
            output_path=Path("/tmp/out"),
            raw_output_path="/tmp/out",
            source_root=Path("/tmp/in"),
        )
        self.assertEqual(result, Path("/tmp/out/nested/example.md"))

    def test_batch_mode_rejects_existing_file_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "out.md"
            output.write_text("taken", encoding="utf-8")
            with self.assertRaises(OutputPathError):
                resolve_output_path(
                    input_path=Path(tmp) / "example.pdf",
                    batch_mode=True,
                    output_path=output,
                    raw_output_path=str(output),
                    source_root=Path(tmp),
                )

    def test_batch_mode_allows_directory_names_with_dots(self) -> None:
        result = resolve_output_path(
            input_path=Path("/tmp/in/example.pdf"),
            batch_mode=True,
            output_path=Path("/tmp/out.v1"),
            raw_output_path="/tmp/out.v1",
            source_root=Path("/tmp/in"),
        )
        self.assertEqual(result, Path("/tmp/out.v1/example.md"))

    def test_duplicate_outputs_are_rejected(self) -> None:
        with self.assertRaises(OutputPathError):
            ensure_no_output_collisions(
                [
                    (Path("/tmp/a.txt"), Path("/tmp/out/same.md")),
                    (Path("/tmp/b.txt"), Path("/tmp/out/same.md")),
                ]
            )
