from __future__ import annotations

from pathlib import Path
from typing import Iterable

from any2md.errors import OutputPathError


def resolve_output_path(
    *,
    input_path: Path,
    batch_mode: bool,
    output_path: Path | None,
    raw_output_path: str | None,
    source_root: Path | None,
) -> Path:
    if not batch_mode:
        if output_path is None:
            return Path(f"{input_path.stem}.md")
        if is_directory_like_output(output_path, raw_output_path):
            return output_path / f"{input_path.stem}.md"
        return output_path

    base_dir = output_path or Path("output")
    if base_dir.exists() and not base_dir.is_dir():
        raise OutputPathError("Batch mode requires --output to be a directory path")
    relative = relative_input_path(input_path=input_path, source_root=source_root)
    return (base_dir / relative).with_suffix(".md")


def ensure_no_output_collisions(pairs: Iterable[tuple[Path, Path]]) -> None:
    collisions = find_output_path_collisions(list(pairs))
    if collisions:
        raise OutputPathError(next(iter(collisions.values())))


def find_output_path_collisions(pairs: Iterable[tuple[Path, Path]]) -> dict[Path, str]:
    seen: dict[Path, Path] = {}
    collisions: dict[Path, str] = {}
    for input_path, output_path in pairs:
        normalized = output_path.resolve()
        if normalized in seen:
            previous = seen[normalized]
            error = f"Output path collision: {previous} and {input_path} both map to {output_path}"
            collisions.setdefault(previous, error)
            collisions[input_path] = error
            continue
        seen[normalized] = input_path
    return collisions


def relative_input_path(*, input_path: Path, source_root: Path | None) -> Path:
    if source_root is None:
        return Path(input_path.name)
    try:
        return input_path.relative_to(source_root)
    except ValueError:
        return Path(input_path.name)


def is_directory_like_output(path: Path, raw_output_path: str | None) -> bool:
    if raw_output_path and raw_output_path.endswith(("/", "\\")):
        return True
    if path.exists():
        return path.is_dir()
    return False
