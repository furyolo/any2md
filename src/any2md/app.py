from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Sequence

from any2md.errors import InputDiscoveryError, OutputPathError
from any2md.paths import find_output_path_collisions, resolve_output_path
from any2md.postprocess import apply_postprocess
from any2md.registry import ConverterRegistry, build_default_registry


class ConversionStatus(str, Enum):
    CONVERTED = "converted"
    FAILED = "failed"
    SKIPPED = "skipped"
    PLANNED = "planned"


@dataclass(slots=True, frozen=True)
class ConversionJob:
    input_path: Path
    source_root: Path | None


@dataclass(slots=True)
class ConversionResult:
    input_path: Path
    output_path: Path | None
    status: ConversionStatus
    message: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status is ConversionStatus.CONVERTED

    @property
    def skipped(self) -> bool:
        return self.status is ConversionStatus.SKIPPED

    @property
    def failed(self) -> bool:
        return self.status is ConversionStatus.FAILED

    @property
    def planned(self) -> bool:
        return self.status is ConversionStatus.PLANNED

    @property
    def error(self) -> str | None:
        return self.message if self.failed else None


@dataclass(slots=True)
class RunSummary:
    results: list[ConversionResult] = field(default_factory=list)

    @property
    def total_count(self) -> int:
        return len(self.results)

    @property
    def converted_count(self) -> int:
        return sum(1 for result in self.results if result.succeeded)

    @property
    def skipped_count(self) -> int:
        return sum(1 for result in self.results if result.skipped)

    @property
    def failure_count(self) -> int:
        return sum(1 for result in self.results if result.failed)

    @property
    def planned_count(self) -> int:
        return sum(1 for result in self.results if result.planned)

    @property
    def success_count(self) -> int:
        return self.converted_count

    @property
    def exit_code(self) -> int:
        if self.failure_count == 0:
            return 0 if self.converted_count > 0 or self.planned_count > 0 else 1
        return 2 if self.converted_count > 0 or self.planned_count > 0 else 1


class ConversionService:
    def __init__(self, registry: ConverterRegistry | None = None) -> None:
        self.registry = registry or build_default_registry()

    def is_batch_mode(self, inputs: Sequence[str]) -> bool:
        return len(inputs) > 1 or any(Path(item).is_dir() for item in inputs)

    def discover_jobs(
        self,
        inputs: Sequence[str],
        *,
        recursive: bool,
    ) -> tuple[list[ConversionJob], list[ConversionResult]]:
        jobs: list[ConversionJob] = []
        results: list[ConversionResult] = []
        discovered_file_count = 0

        for raw_input in inputs:
            candidate = Path(raw_input)
            if not candidate.exists():
                raise InputDiscoveryError(f"Input path does not exist: {candidate}")

            resolved = candidate.resolve()
            if resolved.is_file():
                discovered_file_count += 1
                self._append_discovered_file(
                    jobs=jobs,
                    results=results,
                    input_path=resolved,
                    source_root=resolved.parent,
                )
                continue

            iterator = resolved.rglob("*") if recursive else resolved.glob("*")
            for child in iterator:
                if not child.is_file():
                    continue
                discovered_file_count += 1
                self._append_discovered_file(
                    jobs=jobs,
                    results=results,
                    input_path=child.resolve(),
                    source_root=resolved,
                )

        if discovered_file_count == 0:
            raise InputDiscoveryError("No files were found.")

        return sorted(jobs, key=lambda job: str(job.input_path)), self._sort_results(results)

    def _append_discovered_file(
        self,
        *,
        jobs: list[ConversionJob],
        results: list[ConversionResult],
        input_path: Path,
        source_root: Path | None,
    ) -> None:
        if self.registry.supports(input_path.suffix):
            jobs.append(ConversionJob(input_path=input_path, source_root=source_root))
            return

        results.append(
            ConversionResult(
                input_path=input_path,
                output_path=None,
                status=ConversionStatus.SKIPPED,
                message=self._unsupported_message(input_path),
            )
        )

    def run(
        self,
        *,
        inputs: Sequence[str],
        recursive: bool = False,
        output_path: str | None = None,
        t2s: bool = False,
        dry_run: bool = False,
        force: bool = False,
    ) -> RunSummary:
        batch_mode = self.is_batch_mode(inputs)
        jobs, results = self.discover_jobs(inputs, recursive=recursive)
        output = Path(output_path) if output_path else None

        planned_outputs: dict[Path, Path] = {}
        planning_errors: dict[Path, str] = {}
        for job in jobs:
            try:
                planned_outputs[job.input_path] = resolve_output_path(
                    input_path=job.input_path,
                    batch_mode=batch_mode,
                    output_path=output,
                    raw_output_path=output_path,
                    source_root=job.source_root,
                )
            except OutputPathError as exc:
                planning_errors[job.input_path] = str(exc)

        for input_path, error in find_output_path_collisions(planned_outputs.items()).items():
            planning_errors[input_path] = error
            planned_outputs.pop(input_path, None)

        for input_path, target in list(planned_outputs.items()):
            if target.exists() and not force:
                planning_errors[input_path] = (
                    f"Output already exists: {target}. Use --force to overwrite."
                )
                planned_outputs.pop(input_path, None)

        for job in jobs:
            error = planning_errors.get(job.input_path)
            if error is not None:
                results.append(
                    ConversionResult(
                        input_path=job.input_path,
                        output_path=None,
                        status=ConversionStatus.FAILED,
                        message=error,
                    )
                )
                continue

            target = planned_outputs[job.input_path]
            if dry_run:
                results.append(
                    ConversionResult(
                        input_path=job.input_path,
                        output_path=target,
                        status=ConversionStatus.PLANNED,
                    )
                )
                continue

            try:
                markdown = self.registry.convert(job.input_path)
                markdown = apply_postprocess(markdown, t2s=t2s)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(markdown, encoding="utf-8")
                results.append(
                    ConversionResult(
                        input_path=job.input_path,
                        output_path=target,
                        status=ConversionStatus.CONVERTED,
                    )
                )
            except Exception as exc:
                results.append(
                    ConversionResult(
                        input_path=job.input_path,
                        output_path=None,
                        status=ConversionStatus.FAILED,
                        message=str(exc),
                    )
                )

        return RunSummary(results=self._sort_results(results))

    @staticmethod
    def _sort_results(results: list[ConversionResult]) -> list[ConversionResult]:
        return sorted(results, key=lambda result: str(result.input_path))

    @staticmethod
    def _unsupported_message(path: Path) -> str:
        suffix = path.suffix.lower() or "<no suffix>"
        return f"Unsupported format: {suffix}"


def convert(input_path: str, output_path: str | None = None, t2s: bool = False) -> None:
    service = ConversionService()
    summary = service.run(
        inputs=[input_path],
        output_path=output_path,
        t2s=t2s,
    )
    if summary.converted_count == 1 and summary.failure_count == 0:
        return

    message = next((result.message for result in summary.results if result.message), None)
    raise RuntimeError(message or "Conversion failed")
