import asyncio
from pathlib import Path
from typing import Optional

import aiofiles


class ConcurrencyLimiter:
    def __init__(self, max_concurrent: int):
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def __aenter__(self):
        await self._semaphore.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._semaphore.release()


async def async_read_file(file_path: str | Path, encoding: str = "utf-8") -> str:
    async with aiofiles.open(file_path, mode="r", encoding=encoding) as f:
        return await f.read()


async def async_write_file(
    file_path: str | Path,
    content: str,
    encoding: str = "utf-8",
    mode: str = "w"
) -> None:
    async with aiofiles.open(file_path, mode=mode, encoding=encoding) as f:
        await f.write(content)


async def async_file_exists(file_path: str | Path) -> bool:
    return Path(file_path).exists()
