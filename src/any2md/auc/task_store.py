from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from any2md.auc import AucTask
from any2md.auc.errors import AucTaskNotFoundError


@dataclass
class StoredAucTask:
    task_id: str
    logid: str
    audio_url: str

    def to_auc_task(self) -> AucTask:
        return AucTask(task_id=self.task_id, logid=self.logid)


class AucTaskStore:
    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or (Path.cwd() / ".any2md" / "auc_tasks")

    def save(self, task: AucTask, audio_url: str) -> None:
        self._base_dir.mkdir(parents=True, exist_ok=True)
        record = StoredAucTask(task_id=task.task_id, logid=task.logid, audio_url=audio_url)
        self._path_for(task.task_id).write_text(
            json.dumps(asdict(record), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self, task_id: str) -> StoredAucTask:
        path = self._path_for(task_id)
        if not path.exists():
            raise AucTaskNotFoundError(f"AUC task not found in local cache: {task_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return StoredAucTask(**data)

    def _path_for(self, task_id: str) -> Path:
        return self._base_dir / f"{task_id}.json"
