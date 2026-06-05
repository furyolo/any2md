import asyncio
import tempfile
import unittest
from pathlib import Path

import tests._bootstrap
from any2md.app import ConversionService
from any2md.registry import ConverterRegistry


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

    def test_run_async_reports_batch_output_collisions(self):
        async def run_test():
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                first_dir = root / "first"
                second_dir = root / "second"
                first_dir.mkdir()
                second_dir.mkdir()
                first = first_dir / "same.ok"
                second = second_dir / "same.ok"
                first.write_text("one", encoding="utf-8")
                second.write_text("two", encoding="utf-8")

                registry = ConverterRegistry()
                registry.register([".ok"], lambda path: f"converted:{path.name}")

                summary = await ConversionService(registry=registry).run_async(
                    inputs=[str(first), str(second)],
                    output_path=str(root / "out"),
                )
                return summary

        summary = asyncio.run(run_test())
        self.assertEqual(summary.converted_count, 0)
        self.assertEqual(summary.failure_count, 2)
        self.assertTrue(all(result.error for result in summary.results if result.failed))

    def test_run_async_reconverts_changed_batch_inputs(self):
        async def run_test():
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source_dir = root / "inputs"
                output_dir = root / "output"
                source_dir.mkdir()
                first_source = source_dir / "a.ok"
                second_source = source_dir / "b.ok"
                first_source.write_text("v1-a", encoding="utf-8")
                second_source.write_text("v1-b", encoding="utf-8")

                def content_converter(path: Path) -> str:
                    return path.read_text(encoding="utf-8")

                registry = ConverterRegistry()
                registry.register([".ok"], content_converter)

                service = ConversionService(registry=registry)
                first = await service.run_async(
                    inputs=[str(source_dir)],
                    output_path=str(output_dir),
                )
                second_source.write_text("v2-b", encoding="utf-8")
                second = await service.run_async(
                    inputs=[str(source_dir)],
                    output_path=str(output_dir),
                )

                return (
                    first,
                    second,
                    (output_dir / "a.md").read_text(encoding="utf-8"),
                    (output_dir / "b.md").read_text(encoding="utf-8"),
                )

        first, second, first_output, second_output = asyncio.run(run_test())
        self.assertEqual(first.converted_count, 2)
        self.assertEqual(second.converted_count, 1)
        self.assertEqual(second.already_done_count, 1)
        self.assertEqual(second.failure_count, 0)
        self.assertEqual(first_output, "v1-a")
        self.assertEqual(second_output, "v2-b")

    def test_run_async_resume_failed_only_retries_only_failed_entries(self):
        async def run_test():
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source_dir = root / "inputs"
                output_dir = root / "output"
                source_dir.mkdir()
                good = source_dir / "good.ok"
                bad = source_dir / "bad.bad"
                good.write_text("good", encoding="utf-8")
                bad.write_text("bad", encoding="utf-8")

                def ok_converter(path: Path) -> str:
                    return f"converted:{path.name}"

                def bad_converter(path: Path) -> str:
                    raise RuntimeError("boom")

                first_registry = ConverterRegistry()
                first_registry.register([".ok"], ok_converter)
                first_registry.register([".bad"], bad_converter)

                first = await ConversionService(registry=first_registry).run_async(
                    inputs=[str(source_dir)],
                    output_path=str(output_dir),
                )

                def unexpected_converter_call(path: Path) -> str:
                    raise AssertionError("converter should not be called")

                def fixed_bad_converter(path: Path) -> str:
                    return f"fixed:{path.name}"

                second_registry = ConverterRegistry()
                second_registry.register([".ok"], unexpected_converter_call)
                second_registry.register([".bad"], fixed_bad_converter)

                second = await ConversionService(registry=second_registry).run_async(
                    inputs=[str(source_dir)],
                    output_path=str(output_dir),
                    resume_failed_only=True,
                )

                return first, second, (output_dir / "bad.md").read_text(encoding="utf-8")

        first, second, bad_output = asyncio.run(run_test())
        self.assertEqual(first.converted_count, 1)
        self.assertEqual(first.failure_count, 1)
        self.assertEqual(second.converted_count, 1)
        self.assertEqual(second.failure_count, 0)
        self.assertEqual(second.resume_filtered_count, 1)
        self.assertTrue(any(result.filtered_by_resume_failed_only for result in second.results))
        self.assertEqual(bad_output, "fixed:bad.bad")


if __name__ == "__main__":
    unittest.main()
