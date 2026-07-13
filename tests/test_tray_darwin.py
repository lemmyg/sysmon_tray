"""Unit tests for macOS menu bar helpers."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from ..tray_darwin import (
    _StatusItemDelegate,
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

    def test_status_item_delegate_quit_app(self) -> None:
        on_quit = MagicMock()
        delegate = _StatusItemDelegate.alloc().initWithCallbacks_(
            {
                "on_set_refresh": MagicMock(),
                "on_quit": on_quit,
            },
        )

        delegate.quitApp_(None)

        on_quit.assert_called_once_with()

    def test_status_item_delegate_set_refresh_interval(self) -> None:
        for case in self.cases["status_item_delegate_set_refresh_interval"]:
            with self.subTest(name=case["name"]):
                on_set_refresh = MagicMock()
                delegate = _StatusItemDelegate.alloc().initWithCallbacks_(
                    {
                        "on_set_refresh": on_set_refresh,
                        "on_quit": MagicMock(),
                    },
                )
                sender = MagicMock()
                sender.tag.return_value = case["tag_ms"]

                delegate.setRefreshInterval_(sender)

                on_set_refresh.assert_called_once_with(case["expected_seconds"])


if __name__ == "__main__":
    unittest.main()
