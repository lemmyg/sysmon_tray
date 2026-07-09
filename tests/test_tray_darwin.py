"""Unit tests for macOS menu bar helpers."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from ..tray_darwin import (
    configure_ns_application,
    format_refresh_interval_label,
    seconds_to_milliseconds,
)


def _load_cases() -> dict:
    fixture_path = Path(__file__).with_suffix(".yaml")
    with fixture_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


class TestTrayDarwin(unittest.TestCase):
    """Validate menu bar refresh interval helpers."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = _load_cases()

    def test_format_refresh_interval_label(self) -> None:
        for case in self.cases["format_refresh_interval_label"]:
            with self.subTest(name=case["name"]):
                label = format_refresh_interval_label(
                    case["seconds"],
                    selected=case["selected"],
                )
                self.assertEqual(case["expected"], label)

    def test_seconds_to_milliseconds(self) -> None:
        for case in self.cases["seconds_to_milliseconds"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    seconds_to_milliseconds(case["seconds"]),
                )

    @patch("sysmon_tray.tray_darwin.NSApp")
    @patch("sysmon_tray.tray_darwin.NSApplicationActivationPolicyAccessory", new=1)
    def test_configure_ns_application(self, mock_ns_app: MagicMock) -> None:
        configure_ns_application()

        mock_ns_app.setActivationPolicy_.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
