"""Unit tests for user config load and save helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from ..config import (
    default_config_path,
    load_label_components,
    merge_label_components,
    save_label_components,
)


def _load_cases() -> dict:
    fixture_path = Path(__file__).with_suffix(".yaml")
    with fixture_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


class TestConfig(unittest.TestCase):
    """Validate config path, merge, load, and save helpers."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = _load_cases()

    def test_default_config_path(self) -> None:
        path = default_config_path()
        self.assertEqual("config.yaml", path.name)
        self.assertEqual("sysmon_tray", path.parent.name)
        self.assertEqual("Application Support", path.parent.parent.name)

    def test_merge_label_components(self) -> None:
        for case in self.cases["merge_label_components"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    merge_label_components(case["raw"]),
                )

    def test_load_label_components(self) -> None:
        for case in self.cases["load_label_components"]:
            with self.subTest(name=case["name"]):
                with tempfile.TemporaryDirectory() as temp_dir:
                    config_path = Path(temp_dir) / "config.yaml"
                    if case["file"] is not None:
                        config_path.write_text(case["file"], encoding="utf-8")
                    self.assertEqual(
                        case["expected"],
                        load_label_components(config_path),
                    )

    def test_save_label_components(self) -> None:
        for case in self.cases["save_label_components"]:
            with self.subTest(name=case["name"]):
                with tempfile.TemporaryDirectory() as temp_dir:
                    config_path = Path(temp_dir) / "config.yaml"
                    save_label_components(case["components"], config_path)
                    self.assertEqual(
                        case["expected"],
                        load_label_components(config_path),
                    )
                    with config_path.open(encoding="utf-8") as handle:
                        data = yaml.safe_load(handle)
                    self.assertIn("components", data)


if __name__ == "__main__":
    unittest.main()
