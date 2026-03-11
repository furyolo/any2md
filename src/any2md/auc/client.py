from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import Literal

import httpx

from any2md.auc.errors import AucApiError, AucTimeoutError
from any2md.auc.settings import AucSettings


@dataclass
class AucTask:
    task_id: str
    logid: str


@dataclass
class AucTranscript:
    text: str
    utterances: list | None = None


@dataclass
class AucTaskStatus:
    state: Literal["processing", "completed"]
    transcript: AucTranscript | None = None


class AucClient:
    def __init__(self, settings: AucSettings) -> None:
        self._settings = settings

    def transcribe(self, audio_url: str) -> AucTranscript:
        task = self._submit(audio_url)
        return self._poll(task)

    def submit(self, audio_url: str) -> AucTask:
        return self._submit(audio_url)

    def query(self, task: AucTask) -> AucTaskStatus:
        headers = {
            "Content-Type": "application/json",
            "X-Api-App-Key": self._settings.app_id,
            "X-Api-Access-Key": self._settings.access_key,
            "X-Api-Resource-Id": self._settings.resource_id,
            "X-Api-Request-Id": task.task_id,
            "X-Tt-Logid": task.logid,
        }

        try:
            response = httpx.post(
                self._settings.query_url,
                content=json.dumps({}),
                headers=headers,
                timeout=self._settings.timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AucApiError(f"Failed to query AUC task: {exc}") from exc

        status_code = response.headers.get("X-Api-Status-Code")

        if status_code == "20000000":
            result = response.json()
            text = result.get("result", {}).get("text", "")
            utterances = result.get("result", {}).get("utterances")
            return AucTaskStatus(
                state="completed",
                transcript=AucTranscript(text=text, utterances=utterances),
            )

        if status_code == "20000003":
            raise AucApiError("Audio file contains no speech (silent audio)")

        if status_code in ("20000001", "20000002"):
            return AucTaskStatus(state="processing")

        message = response.headers.get("X-Api-Message", "Unknown error")
        raise AucApiError(f"AUC query failed: {status_code} - {message}")

    def _submit(self, audio_url: str) -> AucTask:
        task_id = str(uuid.uuid4())

        headers = {
            "Content-Type": "application/json",
            "X-Api-App-Key": self._settings.app_id,
            "X-Api-Access-Key": self._settings.access_key,
            "X-Api-Resource-Id": self._settings.resource_id,
            "X-Api-Request-Id": task_id,
            "X-Api-Sequence": "-1",
        }

        payload = {
            "user": {"uid": "any2md_user"},
            "audio": {"url": audio_url},
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_punc": True,
                "enable_ddc": True,
                "show_utterances": False,
                "enable_speaker_info": False,
            },
        }

        try:
            response = httpx.post(
                self._settings.submit_url,
                content=json.dumps(payload),
                headers=headers,
                timeout=self._settings.timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AucApiError(f"Failed to submit AUC task: {exc}") from exc

        status_code = response.headers.get("X-Api-Status-Code")
        if status_code != "20000000":
            message = response.headers.get("X-Api-Message", "Unknown error")
            raise AucApiError(f"AUC submit failed: {status_code} - {message}")

        logid = response.headers.get("X-Tt-Logid", "")
        return AucTask(task_id=task_id, logid=logid)

    def _poll(self, task: AucTask) -> AucTranscript:
        start_time = time.time()
        while True:
            elapsed = time.time() - start_time
            if elapsed > self._settings.max_wait_seconds:
                raise AucTimeoutError(task.task_id, self._settings.max_wait_seconds)

            status = self.query(task)
            if status.state == "completed" and status.transcript is not None:
                return status.transcript

            time.sleep(self._settings.poll_interval)


class AucAsyncClient:
    def __init__(self, settings: AucSettings) -> None:
        self._settings = settings
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=self._settings.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("AucAsyncClient must be used as async context manager")
        return self._client

    async def transcribe(self, audio_url: str) -> AucTranscript:
        task = await self._submit(audio_url)
        return await self._poll(task)

    async def submit(self, audio_url: str) -> AucTask:
        return await self._submit(audio_url)

    async def query(self, task: AucTask) -> AucTaskStatus:
        headers = {
            "Content-Type": "application/json",
            "X-Api-App-Key": self._settings.app_id,
            "X-Api-Access-Key": self._settings.access_key,
            "X-Api-Resource-Id": self._settings.resource_id,
            "X-Api-Request-Id": task.task_id,
            "X-Tt-Logid": task.logid,
        }

        try:
            client = self._get_client()
            response = await client.post(
                self._settings.query_url,
                content=json.dumps({}),
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AucApiError(f"Failed to query AUC task: {exc}") from exc

        status_code = response.headers.get("X-Api-Status-Code")

        if status_code == "20000000":
            result = response.json()
            text = result.get("result", {}).get("text", "")
            utterances = result.get("result", {}).get("utterances")
            return AucTaskStatus(
                state="completed",
                transcript=AucTranscript(text=text, utterances=utterances),
            )

        if status_code == "20000003":
            raise AucApiError("Audio file contains no speech (silent audio)")

        if status_code in ("20000001", "20000002"):
            return AucTaskStatus(state="processing")

        message = response.headers.get("X-Api-Message", "Unknown error")
        raise AucApiError(f"AUC query failed: {status_code} - {message}")

    async def _submit(self, audio_url: str) -> AucTask:
        task_id = str(uuid.uuid4())

        headers = {
            "Content-Type": "application/json",
            "X-Api-App-Key": self._settings.app_id,
            "X-Api-Access-Key": self._settings.access_key,
            "X-Api-Resource-Id": self._settings.resource_id,
            "X-Api-Request-Id": task_id,
            "X-Api-Sequence": "-1",
        }

        payload = {
            "user": {"uid": "any2md_user"},
            "audio": {"url": audio_url},
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_punc": True,
                "enable_ddc": True,
                "show_utterances": False,
                "enable_speaker_info": False,
            },
        }

        try:
            client = self._get_client()
            response = await client.post(
                self._settings.submit_url,
                content=json.dumps(payload),
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AucApiError(f"Failed to submit AUC task: {exc}") from exc

        status_code = response.headers.get("X-Api-Status-Code")
        if status_code != "20000000":
            message = response.headers.get("X-Api-Message", "Unknown error")
            raise AucApiError(f"AUC submit failed: {status_code} - {message}")

        logid = response.headers.get("X-Tt-Logid", "")
        return AucTask(task_id=task_id, logid=logid)

    async def _poll(self, task: AucTask) -> AucTranscript:
        start_time = time.time()
        while True:
            elapsed = time.time() - start_time
            if elapsed > self._settings.max_wait_seconds:
                raise AucTimeoutError(task.task_id, self._settings.max_wait_seconds)

            status = await self.query(task)
            if status.state == "completed" and status.transcript is not None:
                return status.transcript

            await asyncio.sleep(self._settings.poll_interval)
