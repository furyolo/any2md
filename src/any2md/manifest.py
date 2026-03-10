from __future__ import annotations

import json
from pathlib import Path


def manifest_path(output_root: Path) -> Path:
    return output_root / ".any2md-manifest.json"


class BatchManifest:
    def __init__(self, output_root: Path, entries: dict[str, dict] | None = None) -> None:
        self.output_root = output_root
        self.path = manifest_path(output_root)
        self.entries: dict[str, dict] = entries or {}

    @classmethod
    def load(cls, output_root: Path) -> "BatchManifest":
        path = manifest_path(output_root)
        if not path.exists():
            return cls(output_root=output_root)

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls(output_root=output_root)

        entries = payload.get("entries")
        if not isinstance(entries, dict):
            entries = {}
        return cls(output_root=output_root, entries=entries)

    def get(self, output_path: Path) -> dict | None:
        return self.entries.get(self._key(output_path))

    def update(
        self,
        *,
        output_path: Path,
        input_path: str,
        input_hash: str,
        status: str,
        last_run_at: str,
        last_error: str | None = None,
        task_id: str | None = None,
    ) -> None:
        self.entries[self._key(output_path)] = {
            "input_path": input_path,
            "input_hash": input_hash,
            "status": status,
            "last_run_at": last_run_at,
            "last_error": last_error,
            "task_id": task_id,
        }

    def save(self) -> None:
        self.output_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "entries": self.entries,
        }
        temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.path)

    def prune_missing_outputs(self) -> list[str]:
        removed: list[str] = []
        for key in sorted(list(self.entries)):
            if not (self.output_root / key).exists():
                self.entries.pop(key, None)
                removed.append(key)
        return removed

    def _key(self, output_path: Path) -> str:
        try:
            return output_path.relative_to(self.output_root).as_posix()
        except ValueError:
            return output_path.name
