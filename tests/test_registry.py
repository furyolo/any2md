import unittest
from pathlib import Path

import tests._bootstrap
from any2md.errors import UnsupportedFormatError
from any2md.registry import ConverterRegistry, build_default_registry


def sample_converter(path: Path) -> str:
    return path.name


class RegistryTests(unittest.TestCase):
    def test_register_and_lookup_is_case_insensitive(self) -> None:
        registry = ConverterRegistry()
        registry.register([".TXT", "html"], sample_converter)

        self.assertIs(registry.get(".txt"), sample_converter)
        self.assertIs(registry.get(".HTML"), sample_converter)

    def test_unknown_suffix_raises_unsupported_format(self) -> None:
        registry = ConverterRegistry()
        with self.assertRaises(UnsupportedFormatError):
            registry.get(".pdf")

    def test_default_registry_contains_planned_formats(self) -> None:
        registry = build_default_registry()
        for suffix in [
            ".pdf",
            ".epub",
            ".html",
            ".htm",
            ".txt",
            ".docx",
            ".jpg",
            ".jpeg",
            ".png",
        ]:
            self.assertTrue(registry.supports(suffix))

    def test_supports_returns_false_for_suffixless_files(self) -> None:
        registry = build_default_registry()
        self.assertFalse(registry.supports(""))
