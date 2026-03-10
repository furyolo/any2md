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
from any2md.converters.audio import (
    AudioConverter,
    LocalQwenAudioConverter,
    QwenAsrAudioConverter,
    resolve_local_qwen_audio_settings,
)
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
        "--audio-backend",
        choices=["auc", "qwen-local"],
        default="auc",
        help="Choose the audio transcription backend.",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Submit a single remote audio URL and return immediately with a task ID.",
    )
    parser.add_argument(
        "--qwen-runtime",
        choices=["qwen-asr", "chatllm.cpp", "llama.cpp"],
        help="Runtime used by the local Qwen3-ASR backend. Defaults to ANY2MD_QWEN_AUDIO_RUNTIME.",
    )
    parser.add_argument("--qwen-executable", help="Path to the local chatllm.cpp or llama.cpp executable.")
    parser.add_argument("--qwen-model", help="Qwen3-ASR model ID, local pretrained model directory, or runtime-specific model path.")
    parser.add_argument("--qwen-prompt", help="Override the prompt used for local Qwen3-ASR transcription.")
    parser.add_argument("--qwen-language", help="Set the local Qwen3-ASR language hint.")
    parser.add_argument("--qwen-timeout", type=int, help="Timeout in seconds for local Qwen3-ASR runs.")
    parser.add_argument(
        "--qwen-command-template",
        help="Custom command template for the local Qwen3-ASR runtime, mainly for llama.cpp.",
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
    allow_local_audio_inputs = args.audio_backend == "qwen-local"
    if effective_registry is None:
        audio_converter, allow_local_audio_inputs = _build_audio_converter(args, error_stream)
        effective_registry = build_default_registry(audio_converter=audio_converter)

    service = ConversionService(
        registry=effective_registry,
        allow_local_audio_inputs=allow_local_audio_inputs,
    )

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
        if (
            args.recursive
            or args.dry_run
            or args.force
            or args.no_wait
            or args.audio_backend != "auc"
            or args.qwen_runtime is not None
            or args.qwen_executable
            or args.qwen_model
            or args.qwen_prompt
            or args.qwen_language
            or args.qwen_timeout is not None
            or args.qwen_command_template
        ):
            parser.error(
                "--auc-status cannot be combined with conversion flags, --no-wait, or local Qwen options"
            )
        return

    if not args.inputs:
        parser.error("at least one input is required")

    if args.no_wait:
        if args.audio_backend != "auc":
            parser.error("--no-wait is only available with --audio-backend auc")
        if len(args.inputs) != 1:
            parser.error("--no-wait only supports a single direct audio URL")
        if not _is_direct_audio_url(args.inputs[0]):
            parser.error("--no-wait only supports a single direct audio URL")


def _build_audio_converter(args, error_stream):
    if args.audio_backend == "qwen-local":
        settings = resolve_local_qwen_audio_settings(
            runtime=args.qwen_runtime,
            executable=args.qwen_executable,
            model=args.qwen_model,
            prompt=args.qwen_prompt,
            language=args.qwen_language,
            timeout_seconds=args.qwen_timeout,
            command_template=args.qwen_command_template,
        )
        if settings.runtime == "qwen-asr":
            return QwenAsrAudioConverter(settings=settings), True
        return LocalQwenAudioConverter(settings=settings), True

    return (
        AudioConverter(
            task_store=AucTaskStore(),
            wait_for_completion=not args.no_wait,
            progress_callback=_build_audio_progress_callback(error_stream),
        ),
        False,
    )


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
