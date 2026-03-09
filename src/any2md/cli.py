from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence
from urllib.parse import urlparse

from any2md import __version__
from any2md.auc import AucClient, AucMarkdownRenderer
from any2md.auc.settings import load_auc_settings
from any2md.auc.task_store import AucTaskStore
from any2md.app import ConversionService
from any2md.converters.audio import AudioConverter
from any2md.errors import Any2MDError
from any2md.postprocess import apply_postprocess
from any2md.registry import ConverterRegistry, build_default_registry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="any2md", description="Convert files to Markdown.")
    parser.add_argument(
        "inputs",
        nargs="*",
        help="Input files, directories, or direct audio URLs.",
    )
    parser.add_argument("--auc-status", help="Check a previously submitted AUC task by task ID.")
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Submit a single remote audio URL and return immediately with a task ID.",
    )
    parser.add_argument("-r", "--recursive", action="store_true", help="Recursively scan directories.")
    parser.add_argument("--t2s", action="store_true", help="Convert Traditional Chinese to Simplified Chinese.")
    parser.add_argument("-o", "--output", help="Output file path for single-file mode, or directory for batch mode.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan conversions without calling converters or writing files.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output files.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    registry: ConverterRegistry | None = None,
    stdout=None,
    stderr=None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    output_stream = stdout or sys.stdout
    error_stream = stderr or sys.stderr
    _validate_args(parser, args)

    if args.auc_status:
        return _handle_auc_status(args, stdout=output_stream, stderr=error_stream)

    effective_registry = registry
    if effective_registry is None:
        effective_registry = build_default_registry(
            audio_converter=AudioConverter(
                task_store=AucTaskStore(),
                wait_for_completion=not args.no_wait,
                progress_callback=_build_audio_progress_callback(error_stream),
            )
        )

    service = ConversionService(registry=effective_registry)

    try:
        summary = service.run(
            inputs=args.inputs,
            recursive=args.recursive,
            output_path=args.output,
            t2s=args.t2s,
            dry_run=args.dry_run,
            force=args.force,
        )
    except Any2MDError as exc:
        print(str(exc), file=error_stream)
        return 1

    for result in summary.results:
        if result.succeeded:
            detail = f" ({result.message})" if result.message else ""
            print(f"Converted {result.input_path} -> {result.output_path}{detail}", file=error_stream)
        elif result.planned:
            print(f"Planned {result.input_path} -> {result.output_path}", file=error_stream)
        elif result.pending:
            print(f"Processing {result.input_path}: {result.message}", file=error_stream)
            if result.task_id:
                print(f"Task ID: {result.task_id}", file=error_stream)
                print(
                    f"Continue later with: uv run main.py --auc-status {result.task_id}",
                    file=error_stream,
                )
        elif result.skipped:
            print(f"Skipped {result.input_path}: {result.message}", file=error_stream)
        else:
            print(f"Failed {result.input_path}: {result.error}", file=error_stream)

    print(
        (
            "Summary: "
            f"total={summary.total_count} "
            f"converted={summary.converted_count} "
            f"planned={summary.planned_count} "
            f"pending={summary.pending_count} "
            f"skipped={summary.skipped_count} "
            f"failed={summary.failure_count}"
        ),
        file=error_stream,
    )
    return summary.exit_code


def _validate_args(parser: argparse.ArgumentParser, args) -> None:
    if args.auc_status:
        if args.inputs:
            parser.error("--auc-status cannot be used together with conversion inputs")
        if args.recursive or args.dry_run or args.force or args.no_wait:
            parser.error("--auc-status cannot be combined with --recursive, --dry-run, --force, or --no-wait")
        return

    if not args.inputs:
        parser.error("at least one input is required")

    if args.no_wait:
        if len(args.inputs) != 1:
            parser.error("--no-wait only supports a single direct audio URL")
        if not _is_direct_audio_url(args.inputs[0]):
            parser.error("--no-wait only supports a single direct audio URL")


def _is_direct_audio_url(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    suffix = Path(parsed.path).suffix.lower()
    return suffix in AudioConverter.AUDIO_SUFFIXES


def _build_audio_progress_callback(error_stream):
    def report(task, audio_url: str, elapsed_seconds: int) -> None:
        if elapsed_seconds <= 0:
            return
        print(
            f"Audio task {task.task_id} still processing... waited {elapsed_seconds}s",
            file=error_stream,
        )

    return report


def _handle_auc_status(args, *, stdout, stderr) -> int:
    task_store = AucTaskStore()
    stored = task_store.load(args.auc_status)
    client = AucClient(load_auc_settings())
    status = client.query(stored.to_auc_task())

    print(f"Task ID: {stored.task_id}", file=stderr)
    print(f"Audio URL: {stored.audio_url}", file=stderr)

    if status.state == "processing":
        print("Status: processing", file=stderr)
        return 0

    renderer = AucMarkdownRenderer()
    markdown = renderer.render(status.transcript)
    markdown = apply_postprocess(markdown, t2s=args.t2s)

    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(markdown, encoding="utf-8")
        print(f"Completed {stored.task_id} -> {target}", file=stderr)
        return 0

    print("Status: completed", file=stderr)
    print(markdown, file=stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
