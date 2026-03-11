from __future__ import annotations

import argparse
import asyncio
import json
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
from any2md.manifest import BatchManifest, manifest_path
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
        "--manifest-list",
        help="Show entries from .any2md-manifest.json under the given batch output directory.",
    )
    parser.add_argument(
        "--manifest-prune",
        help="Remove manifest entries whose output files no longer exist under the given batch output directory.",
    )
    parser.add_argument(
        "--manifest-status",
        choices=["converted", "failed", "pending", "skipped"],
        help="Filter --manifest-list results by manifest status.",
    )
    parser.add_argument(
        "--audio-backend",
        choices=["auc", "qwen-local"],
        default="qwen-local",
        help="Choose the audio transcription backend (default: qwen-local for offline processing).",
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
    parser.add_argument(
        "--qwen-chunk-duration",
        type=int,
        help="切片时长（秒），默认 600。超过此时长的音频将自动切分后转录。",
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
    parser.add_argument(
        "--resume-failed-only",
        action="store_true",
        help="In batch mode, only retry files marked as failed in .any2md-manifest.json.",
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=5,
        help="Maximum concurrent file conversions (default: 5)",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Force synchronous mode instead of async",
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

    if args.manifest_prune:
        return _handle_manifest_prune(args, stdout=output_stream, stderr=error_stream)

    if args.manifest_list:
        return _handle_manifest_list(args, stdout=output_stream, stderr=error_stream)

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
        if args.sync:
            summary = service.run(
                inputs=args.inputs,
                recursive=args.recursive,
                output_path=args.output,
                t2s=args.t2s,
                dry_run=args.dry_run,
                force=args.force,
                resume_failed_only=args.resume_failed_only,
            )
        else:
            async def progress_callback(result):
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

            summary = asyncio.run(service.run_async(
                inputs=args.inputs,
                recursive=args.recursive,
                output_path=args.output,
                t2s=args.t2s,
                dry_run=args.dry_run,
                force=args.force,
                resume_failed_only=args.resume_failed_only,
                max_concurrent=args.max_concurrent,
                progress_callback=progress_callback,
            ))
    except Any2MDError as exc:
        print(str(exc), file=error_stream)
        return 1

    # Print per-file results for sync mode
    if args.sync:
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
            args.manifest_list
            or args.manifest_prune
            or args.manifest_status
            or args.recursive
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
            or args.qwen_chunk_duration is not None
        ):
            parser.error(
                "--auc-status cannot be combined with conversion flags, --no-wait, or local Qwen options"
            )
        return

    if args.manifest_list:
        if args.inputs:
            parser.error("--manifest-list cannot be used together with conversion inputs")
        if (
            args.auc_status
            or args.manifest_prune
            or args.recursive
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
            or args.qwen_chunk_duration is not None
            or args.output
            or args.t2s
            or args.resume_failed_only
        ):
            parser.error(
                "--manifest-list cannot be combined with conversion flags, output flags, or audio backend options"
            )
        return

    if args.manifest_prune:
        if args.inputs:
            parser.error("--manifest-prune cannot be used together with conversion inputs")
        if (
            args.auc_status
            or args.manifest_list
            or args.manifest_status
            or args.recursive
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
            or args.qwen_chunk_duration is not None
            or args.output
            or args.t2s
            or args.resume_failed_only
        ):
            parser.error(
                "--manifest-prune cannot be combined with conversion flags, output flags, or audio backend options"
            )
        return

    if args.manifest_status:
        parser.error("--manifest-status requires --manifest-list")

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
            chunk_duration_seconds=args.qwen_chunk_duration,
        )
        if settings.runtime == "qwen-asr":
            return (
                QwenAsrAudioConverter(
                    settings=settings,
                    progress_callback=_build_local_qwen_progress_callback(error_stream),
                ),
                True,
            )
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


def _build_local_qwen_progress_callback(error_stream):
    def report(
        *,
        kind: str,
        index: int = 0,
        total: int = 0,
        elapsed_seconds: float | None = None,
        attempt: int | None = None,
        max_attempts: int | None = None,
        error: str | None = None,
        text_length: int | None = None,
        duration_minutes: float | None = None,
    ) -> None:
        if kind == "chunking_start" and duration_minutes is not None:
            print(
                f"检测到长音频 ({duration_minutes:.1f} 分钟)，将切分为 {total} 个片段处理...",
                file=error_stream,
            )
            return

        if kind == "completed" and elapsed_seconds is not None:
            print(
                f"[{index}/{total}] 转录切片 {index}... 完成 ({elapsed_seconds:.1f}s)",
                file=error_stream,
            )
            return

        if kind == "chunk_written" and text_length is not None:
            print(
                f"[{index}/{total}] 已写入 {text_length} 字到输出文件",
                file=error_stream,
            )
            return

        if kind == "retry" and attempt is not None and max_attempts is not None:
            detail = " ".join((error or "").split())
            print(
                f"[{index}/{total}] 转录切片 {index} 失败，重试 {attempt}/{max_attempts}: {detail}",
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


def _handle_manifest_list(args, *, stdout, stderr) -> int:
    manifest, manifest_file = _load_manifest_for_cli(args.manifest_list)
    entries = sorted(manifest.entries.items(), key=lambda item: item[0])
    if args.manifest_status:
        entries = [item for item in entries if item[1].get("status") == args.manifest_status]

    for output_name, payload in entries:
        status = payload.get("status", "unknown")
        input_path = payload.get("input_path", "")
        input_hash = payload.get("input_hash", "")
        last_run_at = payload.get("last_run_at", "")
        detail = f"{status} {output_name} | input={input_path} | hash={input_hash} | time={last_run_at}"
        last_error = payload.get("last_error")
        task_id = payload.get("task_id")
        if task_id:
            detail += f" | task_id={task_id}"
        if last_error:
            detail += f" | error={_single_line(last_error)}"
        print(detail, file=stdout)

    print(
        (
            f"Manifest: path={manifest_file} total={len(manifest.entries)} shown={len(entries)}"
            + (f" filter={args.manifest_status}" if args.manifest_status else "")
        ),
        file=stderr,
    )
    return 0


def _handle_manifest_prune(args, *, stdout, stderr) -> int:
    manifest, manifest_file = _load_manifest_for_cli(args.manifest_prune)
    removed = manifest.prune_missing_outputs()
    manifest.save()

    for key in removed:
        print(f"Pruned {key}", file=stdout)

    print(
        f"Manifest pruned: path={manifest_file} removed={len(removed)} remaining={len(manifest.entries)}",
        file=stderr,
    )
    return 0


def _load_manifest_for_cli(path_value: str) -> tuple[BatchManifest, Path]:
    candidate = Path(path_value)
    if candidate.exists() and candidate.is_file():
        manifest_file = candidate
        output_root = candidate.parent
    elif candidate.name == manifest_path(Path("placeholder")).name:
        manifest_file = candidate
        output_root = candidate.parent
    else:
        output_root = candidate
        manifest_file = manifest_path(output_root)

    if not manifest_file.exists():
        raise Any2MDError(f"Manifest file does not exist: {manifest_file}")

    try:
        payload = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Any2MDError(f"Failed to read manifest file: {manifest_file}") from exc

    entries = payload.get("entries")
    if not isinstance(entries, dict):
        raise Any2MDError(f"Invalid manifest format: {manifest_file}")

    return BatchManifest(output_root=output_root, entries=entries), manifest_file


def _single_line(value: str) -> str:
    return " ".join(value.split())


if __name__ == "__main__":
    raise SystemExit(main())
