from __future__ import annotations

from pathlib import Path


def output_lock_path(output_path: Path) -> Path:
    return output_path.parent / f".{output_path.name}.any2md.lock"


def resume_state_path(output_path: Path) -> Path:
    return output_path.parent / f".{output_path.name}.any2md.resume.json"


def has_resume_state(output_path: Path) -> bool:
    return resume_state_path(output_path).exists()
