from __future__ import annotations

import argparse
import sys
from typing import Sequence

from any2md import __version__
from any2md.app import ConversionService
from any2md.errors import Any2MDError
from any2md.registry import ConverterRegistry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="any2md", description="Convert files to Markdown.")
    parser.add_argument("inputs", nargs="+", help="Input files or directories.")
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

    _ = stdout or sys.stdout
    error_stream = stderr or sys.stderr
    service = ConversionService(registry=registry)

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
            f"skipped={summary.skipped_count} "
            f"failed={summary.failure_count}"
        ),
        file=error_stream,
    )
    return summary.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
