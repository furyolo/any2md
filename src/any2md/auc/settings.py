from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from any2md.auc.errors import AucNotConfiguredError


@dataclass
class AucSettings:
    app_id: str
    access_key: str
    resource_id: str = "volc.seedasr.auc"
    submit_url: str = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
    query_url: str = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
    timeout: int = 30
    poll_interval: float = 1.0
    max_wait_seconds: int = 300


def load_auc_settings() -> AucSettings:
    _load_env_file()

    app_id = os.getenv("ANY2MD_AUC_APP_ID")
    access_key = os.getenv("ANY2MD_AUC_ACCESS_KEY")

    if not app_id or not access_key:
        raise AucNotConfiguredError(
            "AUC credentials not configured. Set ANY2MD_AUC_APP_ID and ANY2MD_AUC_ACCESS_KEY in .env"
        )

    return AucSettings(
        app_id=app_id,
        access_key=access_key,
        resource_id=os.getenv("ANY2MD_AUC_RESOURCE_ID", "volc.seedasr.auc"),
        submit_url=os.getenv(
            "ANY2MD_AUC_SUBMIT_URL",
            "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit",
        ),
        query_url=os.getenv(
            "ANY2MD_AUC_QUERY_URL",
            "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query",
        ),
        timeout=int(os.getenv("ANY2MD_AUC_TIMEOUT", "30")),
        poll_interval=float(os.getenv("ANY2MD_AUC_POLL_INTERVAL", "1.0")),
        max_wait_seconds=int(os.getenv("ANY2MD_AUC_MAX_WAIT_SECONDS", "300")),
    )


def _load_env_file() -> None:
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        return

    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if key and value and key not in os.environ:
                os.environ[key] = value

