from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Sequence
from urllib.parse import unquote, urlparse

from any2md.converters.audio import AudioTaskPendingError
from any2md.errors import InputDiscoveryError, OutputPathError
from any2md.paths import resolve_output_path
from any2md.postprocess import apply_postprocess
from any2md.registry import ConverterRegistry, build_default_registry


class ConversionStatus(str, Enum):
    CONVERTED = "converted"
    FAILED = "failed"
    SKIPPED = "skipped"
    PLANNED = "planned"
    PENDING = "pending"


@dataclass(slots=True, frozen=True)
class ConversionJob:
    sequence: int
    display_input: str
    converter_input: Path | str
    planning_path: Path
    source_root: Path | None


@dataclass(slots=True)
class ConversionResult:
    input_path: str
    output_path: Path | None
    status: ConversionStatus
    message: str | None = None
    task_id: str | None = None

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
    def pending(self) -> bool:
        return self.status is ConversionStatus.PENDING

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
    def pending_count(self) -> int:
        return sum(1 for result in self.results if result.pending)

    @property
    def success_count(self) -> int:
        return self.converted_count + self.pending_count

    @property
    def exit_code(self) -> int:
        if self.failure_count == 0:
            return 0 if self.converted_count > 0 or self.planned_count > 0 or self.pending_count > 0 else 1
        return 2 if self.converted_count > 0 or self.planned_count > 0 or self.pending_count > 0 else 1


class ConversionService:
    REMOTE_MEDIA_SUFFIXES = {
        ".mp3",
        ".wav",
        ".m4a",
        ".aac",
        ".flac",
        ".ogg",
        ".mp4",
        ".mov",
        ".mkv",
        ".avi",
        ".webm",
    }
    LOCAL_AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}

    def __init__(
        self,
        registry: ConverterRegistry | None = None,
        *,
        allow_local_audio_inputs: bool = False,
    ) -> None:
        self.registry = registry or build_default_registry()
        self._allow_local_audio_inputs = allow_local_audio_inputs

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
            if self._is_remote_media_url(raw_input):
                discovered_file_count += 1
                self._append_remote_input(
                    jobs=jobs,
                    results=results,
                    raw_input=raw_input,
                )
                continue

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

        return sorted(jobs, key=lambda job: job.display_input), self._sort_results(results)

    def _append_remote_input(
        self,
        *,
        jobs: list[ConversionJob],
        results: list[ConversionResult],
        raw_input: str,
    ) -> None:
        planning_path = self._remote_planning_path(raw_input)
        if self.registry.supports(planning_path.suffix):
            jobs.append(
                ConversionJob(
                    sequence=len(jobs),
                    display_input=raw_input,
                    converter_input=raw_input,
                    planning_path=planning_path,
                    source_root=None,
                )
            )
            return

        results.append(
            ConversionResult(
                input_path=raw_input,
                output_path=None,
                status=ConversionStatus.SKIPPED,
                message=self._unsupported_message(planning_path),
            )
        )

    def _append_discovered_file(
        self,
        *,
        jobs: list[ConversionJob],
        results: list[ConversionResult],
        input_path: Path,
        source_root: Path | None,
    ) -> None:
        if not self._allow_local_audio_inputs and input_path.suffix.lower() in self.LOCAL_AUDIO_SUFFIXES:
            results.append(
                ConversionResult(
                    input_path=str(input_path),
                    output_path=None,
                    status=ConversionStatus.SKIPPED,
                    message=self._local_audio_message(),
                )
            )
            return

        if self.registry.supports(input_path.suffix):
            jobs.append(
                ConversionJob(
                    sequence=len(jobs),
                    display_input=str(input_path),
                    converter_input=input_path,
                    planning_path=input_path,
                    source_root=source_root,
                )
            )
            return

        results.append(
            ConversionResult(
                input_path=str(input_path),
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

        planned_outputs: dict[int, Path] = {}
        planning_errors: dict[int, str] = {}
        for job in jobs:
            try:
                planned_outputs[job.sequence] = resolve_output_path(
                    input_path=job.planning_path,
                    batch_mode=batch_mode,
                    output_path=output,
                    raw_output_path=output_path,
                    source_root=job.source_root,
                )
            except OutputPathError as exc:
                planning_errors[job.sequence] = str(exc)

        seen_outputs: dict[Path, ConversionJob] = {}
        for job in jobs:
            target = planned_outputs.get(job.sequence)
            if target is None:
                continue

            normalized = target.resolve()
            previous = seen_outputs.get(normalized)
            if previous is None:
                seen_outputs[normalized] = job
                continue

            error = (
                f"Output path collision: {previous.display_input} and "
                f"{job.display_input} both map to {target}"
            )
            planning_errors[previous.sequence] = error
            planning_errors[job.sequence] = error
            planned_outputs.pop(previous.sequence, None)
            planned_outputs.pop(job.sequence, None)

        for job in jobs:
            target = planned_outputs.get(job.sequence)
            if target is None:
                continue

            if target.exists() and not force:
                planning_errors[job.sequence] = (
                    f"Output already exists: {target}. Use --force to overwrite."
                )
                planned_outputs.pop(job.sequence, None)

        for job in jobs:
            error = planning_errors.get(job.sequence)
            if error is not None:
                results.append(
                    ConversionResult(
                        input_path=job.display_input,
                        output_path=None,
                        status=ConversionStatus.FAILED,
                        message=error,
                    )
                )
                continue

            target = planned_outputs[job.sequence]
            if dry_run:
                results.append(
                    ConversionResult(
                        input_path=job.display_input,
                        output_path=target,
                        status=ConversionStatus.PLANNED,
                    )
                )
                continue

            try:
                markdown = self.registry.convert(
                    job.converter_input,
                    suffix=job.planning_path.suffix,
                )
                conversion_message = None
                source_encoding = getattr(markdown, "source_encoding", None)
                if source_encoding:
                    conversion_message = f"encoding={source_encoding}"
                markdown = apply_postprocess(markdown, t2s=t2s)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(markdown, encoding="utf-8")
                results.append(
                    ConversionResult(
                        input_path=job.display_input,
                        output_path=target,
                        status=ConversionStatus.CONVERTED,
                        message=conversion_message,
                    )
                )
            except AudioTaskPendingError as exc:
                results.append(
                    ConversionResult(
                        input_path=job.display_input,
                        output_path=None,
                        status=ConversionStatus.PENDING,
                        message=str(exc),
                        task_id=exc.task.task_id,
                    )
                )
            except Exception as exc:
                results.append(
                    ConversionResult(
                        input_path=job.display_input,
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

    @staticmethod
    def _local_audio_message() -> str:
        return "Local audio files are no longer supported. Provide a direct audio URL instead."

    @classmethod
    def _is_remote_media_url(cls, raw_input: str) -> bool:
        parsed = urlparse(raw_input)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        return cls._remote_planning_path(raw_input).suffix.lower() in cls.REMOTE_MEDIA_SUFFIXES

    @staticmethod
    def _remote_planning_path(raw_input: str) -> Path:
        parsed = urlparse(raw_input)
        filename = Path(unquote(parsed.path)).name or parsed.netloc or "remote-media"
        return Path(filename)


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


