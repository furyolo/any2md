import sys
import types
import unittest

import tests._bootstrap
from any2md.postprocess import apply_postprocess


class DummyOpenCC:
    def __init__(self, config: str) -> None:
        self.config = config

    def convert(self, text: str) -> str:
        return f"{self.config}:{text}"


class PostprocessTests(unittest.TestCase):
    def test_t2s_disabled_returns_original_text(self) -> None:
        self.assertEqual(apply_postprocess("內容", t2s=False), "內容")

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
