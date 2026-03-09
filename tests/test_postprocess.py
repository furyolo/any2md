import sys
import types
import unittest

import tests._bootstrap
from any2md.postprocess import apply_postprocess, clean_ocr_markdown


class DummyOpenCC:
    def __init__(self, config: str) -> None:
        self.config = config

    def convert(self, text: str) -> str:
        return f"{self.config}:{text}"


class PostprocessTests(unittest.TestCase):
    def test_t2s_disabled_returns_original_text(self) -> None:
        self.assertEqual(apply_postprocess("內容", t2s=False), "內容")

    def test_ocr_cleanup_trims_wrapper_text_and_normalizes_markdown(self) -> None:
        raw = (
            "以下是识别结果：\n\n"
            "#标题\n"
            "-第一项\n"
            "1.第二项\n\n"
            "如需我继续整理，请告诉我。"
        )

        self.assertEqual(
            clean_ocr_markdown(raw),
            "# 标题\n- 第一项\n1. 第二项",
        )

    def test_apply_postprocess_supports_ocr_cleanup_before_t2s(self) -> None:
        fake_opencc = types.SimpleNamespace(OpenCC=DummyOpenCC)
        sentinel = object()
        previous = sys.modules.get("opencc", sentinel)
        sys.modules["opencc"] = fake_opencc
        try:
            self.assertEqual(
                apply_postprocess("以下是识别结果：\n\n#標題", ocr_cleanup=True, t2s=True),
                "t2s:# 標題",
            )
        finally:
            if previous is sentinel:
                sys.modules.pop("opencc", None)
            else:
                sys.modules["opencc"] = previous

    def test_ocr_cleanup_converts_aligned_text_block_to_markdown_table(self) -> None:
        raw = (
            "项目  数量  单价\n"
            "苹果  2  3.50\n"
            "香蕉  5  2.00"
        )

        self.assertEqual(
            clean_ocr_markdown(raw),
            "| 项目 | 数量 | 单价 |\n"
            "| --- | --- | --- |\n"
            "| 苹果 | 2 | 3.50 |\n"
            "| 香蕉 | 5 | 2.00 |",
        )

    def test_ocr_cleanup_does_not_turn_markdown_list_into_table(self) -> None:
        raw = "- 第一项  说明\n- 第二项  说明"
        self.assertEqual(clean_ocr_markdown(raw), "- 第一项  说明\n- 第二项  说明")

    def test_ocr_cleanup_skips_ocr_separator_row_when_building_table(self) -> None:
        raw = (
            "项目  数量\n"
            "----  ----\n"
            "苹果  2\n"
            "香蕉  5"
        )

        self.assertEqual(
            clean_ocr_markdown(raw),
            "| 项目 | 数量 |\n"
            "| --- | --- |\n"
            "| 苹果 | 2 |\n"
            "| 香蕉 | 5 |",
        )

    def test_t2s_uses_lazy_opencc_import(self) -> None:
        fake_opencc = types.SimpleNamespace(OpenCC=DummyOpenCC)
        sentinel = object()
        previous = sys.modules.get("opencc", sentinel)
        sys.modules["opencc"] = fake_opencc
        try:
            self.assertEqual(apply_postprocess("內容", t2s=True), "t2s:內容")
        finally:
            if previous is sentinel:
                sys.modules.pop("opencc", None)
            else:
                sys.modules["opencc"] = previous
