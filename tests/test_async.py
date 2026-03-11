import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import tests._bootstrap
from any2md.async_utils import (
    ConcurrencyLimiter,
    async_file_exists,
    async_read_file,
    async_write_file,
)
from any2md.app import ConversionService
from any2md.registry import ConverterRegistry


class AsyncUtilsTests(unittest.TestCase):
    def test_concurrency_limiter_limits_concurrent_tasks(self):
        async def run_test():
            limiter = ConcurrencyLimiter(max_concurrent=2)
            active_count = 0
            max_active = 0
            results = []

            async def task(task_id: int):
                nonlocal active_count, max_active
                async with limiter:
                    active_count += 1
                    max_active = max(max_active, active_count)
                    await asyncio.sleep(0.01)
                    active_count -= 1
                    results.append(task_id)

            await asyncio.gather(*[task(i) for i in range(5)])
            return max_active, results

        max_active, results = asyncio.run(run_test())
        self.assertEqual(max_active, 2)
        self.assertEqual(len(results), 5)

    def test_async_read_write_file(self):
        async def run_test():
            with tempfile.TemporaryDirectory() as tmp:
                file_path = Path(tmp) / "test.txt"
                content = "Hello async world"

                await async_write_file(file_path, content)
                read_content = await async_read_file(file_path)

                return read_content

        result = asyncio.run(run_test())
        self.assertEqual(result, "Hello async world")

    def test_async_file_exists(self):
        async def run_test():
            with tempfile.TemporaryDirectory() as tmp:
                existing = Path(tmp) / "exists.txt"
                existing.write_text("content")
                non_existing = Path(tmp) / "not_exists.txt"

                exists_result = await async_file_exists(existing)
                not_exists_result = await async_file_exists(non_existing)

                return exists_result, not_exists_result

        exists, not_exists = asyncio.run(run_test())
        self.assertTrue(exists)
        self.assertFalse(not_exists)


class AucAsyncClientTests(unittest.TestCase):
    def test_auc_async_client_transcribe(self):
        async def run_test():
            from any2md.auc.client import AucAsyncClient, AucTranscript
            from any2md.auc.settings import AucSettings

            settings = AucSettings(
                app_id="test-app",
                access_key="test-key",
                resource_id="test-resource",
            )

            client = AucAsyncClient(settings)

            with patch.object(client, "_submit") as mock_submit, patch.object(
                client, "_poll"
            ) as mock_poll:
                mock_submit.return_value = MagicMock(task_id="task-123", logid="log-456")
                mock_poll.return_value = AucTranscript(text="test transcript")

                result = await client.transcribe("https://example.com/audio.mp3")

                return result.text

        result = asyncio.run(run_test())
        self.assertEqual(result, "test transcript")


class OcrAsyncTests(unittest.TestCase):
    def test_ocr_image_async_basic(self):
        async def run_test():
            from any2md.ocr import ocr_image_async, LlmOcrSettings

            settings = LlmOcrSettings(
                api_base="https://api.example.com/v1",
                api_key="test-key",
                model="test-model",
            )

            with tempfile.TemporaryDirectory() as tmp:
                image_path = Path(tmp) / "test.png"
                image_path.write_bytes(b"fake-image-data")

                with patch("httpx.AsyncClient") as mock_client_class:
                    mock_client = AsyncMock()
                    mock_response = MagicMock()  # Changed from AsyncMock to MagicMock
                    mock_response.json.return_value = {
                        "choices": [{"message": {"content": "OCR result text"}}]
                    }
                    mock_response.raise_for_status = MagicMock()
                    mock_client.post = AsyncMock(return_value=mock_response)  # post is async
                    mock_client.__aenter__.return_value = mock_client
                    mock_client.__aexit__.return_value = AsyncMock()
                    mock_client_class.return_value = mock_client

                    result = await ocr_image_async(image_path, settings)

                    return result

        result = asyncio.run(run_test())
        self.assertEqual(result, "OCR result text")


class ConversionServiceAsyncTests(unittest.TestCase):
    def test_run_async_processes_files_concurrently(self):
        async def run_test():
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                file1 = root / "file1.ok"
                file2 = root / "file2.ok"
                file1.write_text("content1")
                file2.write_text("content2")

                call_order = []

                def sync_converter(path: Path) -> str:
                    call_order.append(path.name)
                    return f"converted:{path.name}"

                registry = ConverterRegistry()
                registry.register([".ok"], sync_converter)

                service = ConversionService(registry=registry)
                summary = await service.run_async(
                    inputs=[str(file1), str(file2)],
                    output_path=str(root / "output"),
                    max_concurrent=2,
                )

                return summary.converted_count, summary.failure_count, len(call_order)

        converted, failed, call_count = asyncio.run(run_test())
        self.assertEqual(converted, 2)
        self.assertEqual(failed, 0)
        self.assertEqual(call_count, 2)


if __name__ == "__main__":
    unittest.main()
