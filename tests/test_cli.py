import json
import os
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import tests._bootstrap
from any2md.auc.client import AucTask, AucTranscript
from any2md.auc.task_store import AucTaskStore
from any2md.cli import _build_audio_converter, build_parser, main
from any2md.converters.audio import AudioTaskPendingError
from any2md.converters.text import text_to_markdown
from any2md.registry import ConverterRegistry


def ok_converter(path: Path) -> str:
    return "ok"


def bad_converter(path: Path) -> str:
    raise RuntimeError("boom")


def unexpected_converter_call(path: Path) -> str:
    raise AssertionError("converter should not be called")


class FakeAucStatusClient:
    def __init__(self, _settings) -> None:
        self._settings = _settings

    def query(self, task):
        return type(
            "FakeStatus",
            (),
            {"state": "completed", "transcript": AucTranscript(text="audio-result")},
        )()


class CliTests(unittest.TestCase):
    def test_qwen_runtime_uses_env_when_cli_flag_is_omitted(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["demo.mp3", "--audio-backend", "qwen-local"])

        with patch.dict(
            os.environ,
            {
                "ANY2MD_QWEN_AUDIO_RUNTIME": "qwen-asr",
                "ANY2MD_QWEN_AUDIO_MODEL": "Qwen/Qwen3-ASR-1.7B",
            },
            clear=False,
        ):
            converter, allow_local_audio_inputs = _build_audio_converter(args, StringIO())

        self.assertTrue(allow_local_audio_inputs)
        self.assertEqual(converter._settings.runtime, "qwen-asr")

    @patch("any2md.cli.build_default_registry")
    def test_cli_no_wait_reports_pending_task(self, mocked_registry_builder) -> None:
        def pending_converter(path: str) -> str:
            raise AudioTaskPendingError(
                task=AucTask(task_id="task-123", logid="log-123"),
                audio_url=path,
                reason="Audio task submitted and still processing.",
            )

        registry = ConverterRegistry()
        registry.register([".mp3"], pending_converter)
        mocked_registry_builder.return_value = registry

        stdout = StringIO()
        stderr = StringIO()
        code = main(
            ["https://example.com/audio.mp3", "--no-wait"],
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Processing https://example.com/audio.mp3", stderr.getvalue())
        self.assertIn("Task ID: task-123", stderr.getvalue())
        self.assertIn("--auc-status task-123", stderr.getvalue())
        self.assertIn(
            "Summary: total=1 converted=0 planned=0 pending=1 skipped=0 failed=0",
            stderr.getvalue(),
        )

    @patch("any2md.cli.AucClient", FakeAucStatusClient)
    @patch("any2md.cli.load_auc_settings", return_value=object())
    def test_cli_auc_status_outputs_transcript(self, _mocked_settings) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original_cwd = Path.cwd()
            os.chdir(root)
            try:
                AucTaskStore().save(
                    AucTask(task_id="task-456", logid="log-456"),
                    "https://example.com/audio.mp3",
                )

                stdout = StringIO()
                stderr = StringIO()
                code = main(
                    ["--auc-status", "task-456"],
                    stdout=stdout,
                    stderr=stderr,
                )
            finally:
                os.chdir(original_cwd)

        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue().strip(), "audio-result")
        self.assertIn("Task ID: task-456", stderr.getvalue())
        self.assertIn("Status: completed", stderr.getvalue())

    def test_cli_manifest_list_outputs_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "output"
            output_dir.mkdir()
            (output_dir / ".any2md-manifest.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "entries": {
                            "a.md": {
                                "input_path": "a.ok",
                                "input_hash": "sha256:aaa",
                                "status": "converted",
                                "last_run_at": "2026-03-10T10:00:00Z",
                                "last_error": None,
                                "task_id": None,
                            },
                            "b.md": {
                                "input_path": "b.bad",
                                "input_hash": "sha256:bbb",
                                "status": "failed",
                                "last_run_at": "2026-03-10T11:00:00Z",
                                "last_error": "RuntimeError: boom",
                                "task_id": None,
                            },
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            stdout = StringIO()
            stderr = StringIO()
            code = main(
                ["--manifest-list", str(output_dir)],
                stdout=stdout,
                stderr=stderr,
            )

            self.assertEqual(code, 0)
            self.assertIn("converted a.md", stdout.getvalue())
            self.assertIn("failed b.md", stdout.getvalue())
            self.assertIn("Manifest: path=", stderr.getvalue())
            self.assertIn("shown=2", stderr.getvalue())

    def test_cli_manifest_list_supports_status_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "output"
            output_dir.mkdir()
            (output_dir / ".any2md-manifest.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "entries": {
                            "a.md": {
                                "input_path": "a.ok",
                                "input_hash": "sha256:aaa",
                                "status": "converted",
                                "last_run_at": "2026-03-10T10:00:00Z",
                                "last_error": None,
                                "task_id": None,
                            },
                            "b.md": {
                                "input_path": "b.bad",
                                "input_hash": "sha256:bbb",
                                "status": "failed",
                                "last_run_at": "2026-03-10T11:00:00Z",
                                "last_error": "RuntimeError: boom",
                                "task_id": None,
                            },
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            stdout = StringIO()
            stderr = StringIO()
            code = main(
                ["--manifest-list", str(output_dir), "--manifest-status", "failed"],
                stdout=stdout,
                stderr=stderr,
            )

            self.assertEqual(code, 0)
            self.assertNotIn("converted a.md", stdout.getvalue())
            self.assertIn("failed b.md", stdout.getvalue())
            self.assertIn("filter=failed", stderr.getvalue())

    def test_cli_manifest_status_requires_manifest_list(self) -> None:
        with self.assertRaises(SystemExit):
            main(["--manifest-status", "failed"], stdout=StringIO(), stderr=StringIO())

    def test_cli_manifest_prune_removes_missing_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "output"
            output_dir.mkdir()
            (output_dir / "keep.md").write_text("keep", encoding="utf-8")
            (output_dir / ".any2md-manifest.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "entries": {
                            "keep.md": {
                                "input_path": "keep.ok",
                                "input_hash": "sha256:keep",
                                "status": "converted",
                                "last_run_at": "2026-03-10T10:00:00Z",
                                "last_error": None,
                                "task_id": None,
                            },
                            "missing.md": {
                                "input_path": "missing.ok",
                                "input_hash": "sha256:missing",
                                "status": "failed",
                                "last_run_at": "2026-03-10T11:00:00Z",
                                "last_error": "RuntimeError: boom",
                                "task_id": None,
                            },
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            stdout = StringIO()
            stderr = StringIO()
            code = main(
                ["--manifest-prune", str(output_dir)],
                stdout=stdout,
                stderr=stderr,
            )

            self.assertEqual(code, 0)
            self.assertIn("Pruned missing.md", stdout.getvalue())
            self.assertIn("removed=1", stderr.getvalue())

            payload = json.loads((output_dir / ".any2md-manifest.json").read_text(encoding="utf-8"))
            self.assertIn("keep.md", payload["entries"])
            self.assertNotIn("missing.md", payload["entries"])

    def test_cli_manifest_prune_cannot_be_combined_with_manifest_list(self) -> None:
        with self.assertRaises(SystemExit):
            main(
                ["--manifest-prune", "output", "--manifest-list", "output"],
                stdout=StringIO(),
                stderr=StringIO(),
            )

    def test_cli_accepts_remote_audio_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "audio.md"
            received: list[str] = []

            def remote_converter(path: str) -> str:
                received.append(path)
                return "ok"

            registry = ConverterRegistry()
            registry.register([".mp3"], remote_converter)

            stdout = StringIO()
            stderr = StringIO()
            code = main(
                ["https://example.com/audio.mp3", "--output", str(output)],
                registry=registry,
                stdout=stdout,
                stderr=stderr,
            )

            self.assertEqual(code, 0)
            self.assertEqual(stdout.getvalue(), "")
            self.assertTrue(output.exists())
            self.assertEqual(received, ["https://example.com/audio.mp3"])
            self.assertIn("Converted https://example.com/audio.mp3", stderr.getvalue())

    def test_cli_reports_remote_video_url_as_skipped(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        code = main(
            ["https://example.com/video.mp4"],
            registry=ConverterRegistry(),
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Skipped https://example.com/video.mp4", stderr.getvalue())
        self.assertIn("Unsupported format: .mp4", stderr.getvalue())

    def test_cli_reports_local_audio_file_as_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "audio.mp3"
            source.write_bytes(b"fake-audio")

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
            self.assertIn("Local audio files are no longer supported", stderr.getvalue())

    def test_cli_accepts_local_audio_file_with_qwen_local_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "audio.mp3"
            output = root / "audio.md"
            source.write_bytes(b"fake-audio")
            received: list[Path] = []

            def local_converter(path: Path) -> str:
                received.append(path)
                return "local-qwen-ok"

            registry = ConverterRegistry()
            registry.register([".mp3"], local_converter)

            stdout = StringIO()
            stderr = StringIO()
            code = main(
                [str(source), "--audio-backend", "qwen-local", "--output", str(output)],
                registry=registry,
                stdout=stdout,
                stderr=stderr,
            )

            self.assertEqual(code, 0)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(received, [source.resolve()])
            self.assertEqual(output.read_text(encoding="utf-8"), "local-qwen-ok")
            self.assertIn("Converted", stderr.getvalue())

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
                "Summary: total=2 converted=1 planned=0 pending=0 skipped=0 failed=1",
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
                "Summary: total=1 converted=0 planned=0 pending=0 skipped=1 failed=0",
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

    def test_cli_batch_rerun_skips_already_converted_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "inputs"
            output_dir = root / "output"
            source_dir.mkdir()
            (source_dir / "a.ok").write_text("a", encoding="utf-8")
            (source_dir / "b.ok").write_text("b", encoding="utf-8")

            registry = ConverterRegistry()
            registry.register([".ok"], ok_converter)

            first_stdout = StringIO()
            first_stderr = StringIO()
            first_code = main(
                [str(source_dir), "--output", str(output_dir)],
                registry=registry,
                stdout=first_stdout,
                stderr=first_stderr,
            )

            second_stdout = StringIO()
            second_stderr = StringIO()
            second_code = main(
                [str(source_dir), "--output", str(output_dir)],
                registry=registry,
                stdout=second_stdout,
                stderr=second_stderr,
            )

            self.assertEqual(first_code, 0)
            self.assertEqual(second_code, 0)
            self.assertIn("Skipped", second_stderr.getvalue())
            self.assertIn("Already converted", second_stderr.getvalue())
            self.assertIn(
                "Summary: total=2 converted=0 planned=0 pending=0 skipped=2 failed=0",
                second_stderr.getvalue(),
            )

    def test_cli_resume_failed_only_retries_failed_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "inputs"
            output_dir = root / "output"
            source_dir.mkdir()
            good = source_dir / "good.ok"
            bad = source_dir / "bad.bad"
            good.write_text("good", encoding="utf-8")
            bad.write_text("bad", encoding="utf-8")

            first_registry = ConverterRegistry()
            first_registry.register([".ok"], ok_converter)
            first_registry.register([".bad"], bad_converter)

            first_code = main(
                [str(source_dir), "--output", str(output_dir)],
                registry=first_registry,
                stdout=StringIO(),
                stderr=StringIO(),
            )

            second_registry = ConverterRegistry()
            second_registry.register([".ok"], unexpected_converter_call)
            second_registry.register([".bad"], lambda _path: "fixed")

            second_stdout = StringIO()
            second_stderr = StringIO()
            second_code = main(
                [str(source_dir), "--output", str(output_dir), "--resume-failed-only"],
                registry=second_registry,
                stdout=second_stdout,
                stderr=second_stderr,
            )

            self.assertEqual(first_code, 2)
            self.assertEqual(second_code, 0)
            self.assertIn("Skipped", second_stderr.getvalue())
            self.assertIn("Skipped by --resume-failed-only", second_stderr.getvalue())
            self.assertIn("Converted", second_stderr.getvalue())


