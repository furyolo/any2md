from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Sequence
from urllib.parse import unquote, urlparse

from any2md.converters.audio import AudioTaskPendingError
from any2md.errors import InputDiscoveryError, OutputPathError
from any2md.io_state import has_resume_state, resume_state_path
from any2md.locking import OutputFileLock
from any2md.manifest import BatchManifest
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

    @property
    def already_done(self) -> bool:
        return self.skipped and bool(self.message and self.message.startswith("Already converted:"))

    @property
    def filtered_by_resume_failed_only(self) -> bool:
        return self.skipped and bool(
            self.message and self.message.startswith("Skipped by --resume-failed-only:")
        )


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
        return (
            self.converted_count
            + self.pending_count
            + self.already_done_count
            + self.resume_filtered_count
        )

    @property
    def already_done_count(self) -> int:
        return sum(1 for result in self.results if result.already_done)

    @property
    def resume_filtered_count(self) -> int:
        return sum(1 for result in self.results if result.filtered_by_resume_failed_only)

    @property
    def exit_code(self) -> int:
        if self.failure_count == 0:
            return 0 if self._has_effective_success else 1
        return 2 if self._has_effective_success else 1

    @property
    def _has_effective_success(self) -> bool:
        return (
            self.converted_count > 0
            or self.planned_count > 0
            or self.pending_count > 0
            or self.already_done_count > 0
            or self.resume_filtered_count > 0
        )


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
        resume_failed_only: bool = False,
    ) -> RunSummary:
        batch_mode = self.is_batch_mode(inputs)
        jobs, discovered_results = self.discover_jobs(inputs, recursive=recursive)
        output = Path(output_path) if output_path else None
        results: list[ConversionResult] = []
        manifest = self._load_batch_manifest(batch_mode=batch_mode, output_path=output)
        hash_cache: dict[str, str] = {}

        def append_result(
            result: ConversionResult,
            *,
            job: ConversionJob | None = None,
            persist_manifest: bool = True,
        ) -> None:
            results.append(result)
            if manifest is None or dry_run or not persist_manifest:
                return

            input_hash = self._input_hash_for_result(result=result, job=job, hash_cache=hash_cache)
            if input_hash is None:
                return

            status = self._manifest_status_for_result(result)
            if status is None:
                return

            output_target = result.output_path
            if output_target is None and job is not None:
                output_target = planned_outputs.get(job.sequence)
            if output_target is None:
                return

            manifest.update(
                output_path=output_target,
                input_path=result.input_path,
                input_hash=input_hash,
                status=status,
                last_run_at=self._current_timestamp(),
                last_error=None if status == "converted" else result.message,
                task_id=result.task_id,
            )

        for result in discovered_results:
            append_result(result)

        planned_outputs: dict[int, Path] = {}
        planning_errors: dict[int, str] = {}
        planning_skips: dict[int, str] = {}
        overwrite_jobs: set[int] = set()
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
            if resume_failed_only and batch_mode:
                target = planned_outputs.get(job.sequence)
                if target is None:
                    continue

                manifest_entry = manifest.get(target) if manifest is not None else None
                if manifest_entry is None:
                    planning_skips[job.sequence] = self._resume_failed_only_skip_message(
                        "no manifest entry"
                    )
                    planned_outputs.pop(job.sequence, None)
                    continue

                if manifest_entry.get("status") != "failed":
                    planning_skips[job.sequence] = self._resume_failed_only_skip_message(
                        f"last status is {manifest_entry.get('status', 'unknown')}"
                    )
                    planned_outputs.pop(job.sequence, None)

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
                if not has_resume_state(target):
                    should_remove_planned_output = True
                    if batch_mode:
                        manifest_entry = manifest.get(target) if manifest is not None else None
                        if manifest_entry is None:
                            planning_skips[job.sequence] = self._already_done_message(target)
                        else:
                            current_hash = self._cached_input_hash(job.converter_input, hash_cache)
                            if (
                                manifest_entry.get("status") == "converted"
                                and manifest_entry.get("input_hash") == current_hash
                            ):
                                planning_skips[job.sequence] = self._already_done_message(target)
                            else:
                                overwrite_jobs.add(job.sequence)
                                should_remove_planned_output = False
                    else:
                        planning_errors[job.sequence] = (
                            f"Output already exists: {target}. Use --force to overwrite."
                        )
                    if should_remove_planned_output:
                        planned_outputs.pop(job.sequence, None)

        for job in jobs:
            error = planning_errors.get(job.sequence)
            if error is not None:
                append_result(
                    ConversionResult(
                        input_path=job.display_input,
                        output_path=None,
                        status=ConversionStatus.FAILED,
                        message=error,
                    ),
                    job=job,
                )
                continue

            skip_message = planning_skips.get(job.sequence)
            if skip_message is not None:
                persist_manifest = not skip_message.startswith("Skipped by --resume-failed-only:")
                append_result(
                    ConversionResult(
                        input_path=job.display_input,
                        output_path=planned_outputs.get(job.sequence),
                        status=ConversionStatus.SKIPPED,
                        message=skip_message,
                    ),
                    job=job,
                    persist_manifest=persist_manifest,
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
                # 提前创建输出目录
                target.parent.mkdir(parents=True, exist_ok=True)
                should_overwrite = force or job.sequence in overwrite_jobs
                if should_overwrite:
                    resume_state_path(target).unlink(missing_ok=True)

                with OutputFileLock(target):
                    # 尝试流式输出（如果 converter 支持）
                    markdown = self.registry.convert(
                        job.converter_input,
                        suffix=job.planning_path.suffix,
                        output_path=target,
                    )
                    conversion_message = None
                    source_encoding = getattr(markdown, "source_encoding", None)
                    if source_encoding:
                        conversion_message = f"encoding={source_encoding}"

                    # 应用后处理
                    if t2s:
                        # 先读取流式写入的完整内容（如果存在）
                        if target.exists() and target.stat().st_size > 0:
                            markdown = target.read_text(encoding="utf-8")
                        markdown = apply_postprocess(markdown, t2s=True)
                        target.write_text(markdown, encoding="utf-8")
                    elif should_overwrite or not target.exists() or target.stat().st_size == 0:
                        # 如果 converter 不支持流式输出，写入文件
                        target.write_text(markdown, encoding="utf-8")

                append_result(
                    ConversionResult(
                        input_path=job.display_input,
                        output_path=target,
                        status=ConversionStatus.CONVERTED,
                        message=conversion_message,
                    ),
                    job=job,
                )
            except AudioTaskPendingError as exc:
                append_result(
                    ConversionResult(
                        input_path=job.display_input,
                        output_path=target,
                        status=ConversionStatus.PENDING,
                        message=str(exc),
                        task_id=exc.task.task_id,
                    ),
                    job=job,
                )
            except Exception as exc:
                append_result(
                    ConversionResult(
                        input_path=job.display_input,
                        output_path=target,
                        status=ConversionStatus.FAILED,
                        message=self._format_error(exc, target),
                    ),
                    job=job,
                )

        if manifest is not None and not dry_run:
            manifest.save()

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

    @staticmethod
    def _already_done_message(output_path: Path) -> str:
        return f"Already converted: {output_path}. Use --force to overwrite."

    @staticmethod
    def _resume_failed_only_skip_message(reason: str) -> str:
        return f"Skipped by --resume-failed-only: {reason}"

    @staticmethod
    def _load_batch_manifest(*, batch_mode: bool, output_path: Path | None) -> BatchManifest | None:
        if not batch_mode:
            return None
        output_root = output_path or Path("output")
        return BatchManifest.load(output_root)

    @staticmethod
    def _current_timestamp() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _input_hash_for_result(
        self,
        *,
        result: ConversionResult,
        job: ConversionJob | None,
        hash_cache: dict[str, str],
    ) -> str | None:
        if job is not None:
            return self._cached_input_hash(job.converter_input, hash_cache)

        raw_input = result.input_path
        candidate = Path(raw_input)
        if candidate.exists() and candidate.is_file():
            return self._cached_input_hash(candidate.resolve(), hash_cache)
        if self._is_remote_media_url(raw_input):
            return self._cached_input_hash(raw_input, hash_cache)
        return None

    def _cached_input_hash(self, converter_input: Path | str, hash_cache: dict[str, str]) -> str:
        cache_key = str(converter_input)
        cached = hash_cache.get(cache_key)
        if cached is not None:
            return cached

        digest = self._compute_input_hash(converter_input)
        hash_cache[cache_key] = digest
        return digest

    @staticmethod
    def _compute_input_hash(converter_input: Path | str) -> str:
        digest = hashlib.sha256()
        if isinstance(converter_input, Path):
            with converter_input.open("rb") as handle:
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
            return f"sha256:{digest.hexdigest()}"

        digest.update(converter_input.encode("utf-8"))
        return f"sha256:{digest.hexdigest()}"

    @staticmethod
    def _manifest_status_for_result(result: ConversionResult) -> str | None:
        if result.succeeded or result.already_done:
            return "converted"
        if result.failed:
            return "failed"
        if result.pending:
            return "pending"
        if result.skipped:
            return "skipped"
        return None

    @staticmethod
    def _format_error(exc: Exception, output_path: Path | None) -> str:
        detail = " ".join(str(exc).split()) or exc.__class__.__name__
        parts = [f"{exc.__class__.__name__}: {detail}"]
        if output_path is not None:
            parts.append(f"output={output_path}")

        cause = exc.__cause__
        if cause is not None:
            cause_detail = " ".join(str(cause).split()) or cause.__class__.__name__
            if cause_detail != detail:
                parts.append(f"cause={cause.__class__.__name__}: {cause_detail}")

        return " | ".join(parts)

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
