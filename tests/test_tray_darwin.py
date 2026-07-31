"""Unit tests for macOS menu bar helpers."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from ..tray_common import (
    default_label_components,
    format_about_text,
    label_component_key_for_tag,
    toggle_label_component,
)
from ..tray_darwin import (
    _StatusItemDelegate,
    ACTIVITY_MONITOR_APP_PATH,
    about_menu_text_field,
    configure_ns_application,
    format_refresh_interval_label,
    seconds_to_milliseconds,
    status_item_click_action,
    status_item_length_for_title_width,
)


def _load_cases() -> dict:
    fixture_path = Path(__file__).with_suffix(".yaml")
    with fixture_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _delegate_callbacks(**overrides: object) -> dict[str, object]:
    callbacks = {
        "on_set_refresh": MagicMock(),
        "on_toggle_component": MagicMock(),
        "on_quit": MagicMock(),
        "status_item": MagicMock(),
        "menu": MagicMock(),
    }
    callbacks.update(overrides)
    return callbacks


class TestTrayDarwin(unittest.TestCase):
    """Validate menu bar refresh interval helpers."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = _load_cases()

    def test_format_refresh_interval_label(self) -> None:
        for case in self.cases["format_refresh_interval_label"]:
            with self.subTest(name=case["name"]):
                label = format_refresh_interval_label(case["seconds"])
                self.assertEqual(case["expected"], label)

    def test_format_about_text(self) -> None:
        for case in self.cases["format_about_text"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(case["expected"], format_about_text())

    @patch("sysmon_tray.tray_darwin.NSTextField")
    @patch("sysmon_tray.tray_darwin.NSFont")
    def test_about_menu_text_field(
        self,
        mock_ns_font: MagicMock,
        mock_ns_text_field: MagicMock,
    ) -> None:
        field = MagicMock()
        field.fittingSize.return_value.height = 48.0
        mock_ns_text_field.alloc.return_value.initWithFrame_.return_value = field

        result = about_menu_text_field(width=280.0)

        self.assertIs(result, field)
        field.setStringValue_.assert_called_once_with(format_about_text())
        field.setAlignment_.assert_called_once()
        field.setFrameSize_.assert_called_once_with((280.0, 48.0))

    def test_seconds_to_milliseconds(self) -> None:
        for case in self.cases["seconds_to_milliseconds"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    seconds_to_milliseconds(case["seconds"]),
                )

    def test_status_item_length_for_title_width(self) -> None:
        for case in self.cases["status_item_length_for_title_width"]:
            with self.subTest(name=case["name"]):
                if case["padding"] is None:
                    length = status_item_length_for_title_width(case["title_width"])
                else:
                    length = status_item_length_for_title_width(
                        case["title_width"],
                        padding=case["padding"],
                    )
                self.assertEqual(case["expected"], length)

    @patch("sysmon_tray.tray_darwin.NSApp")
    @patch("sysmon_tray.tray_darwin.NSApplicationActivationPolicyAccessory", new=1)
    def test_configure_ns_application(self, mock_ns_app: MagicMock) -> None:
        configure_ns_application()

        mock_ns_app.setActivationPolicy_.assert_called_once_with(1)

    def test_default_label_components(self) -> None:
        components = default_label_components()
        self.assertTrue(components)
        self.assertTrue(all(components.values()))

    def test_toggle_label_component(self) -> None:
        for case in self.cases["toggle_label_component"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    toggle_label_component(case["components"], case["key"]),
                )

    def test_label_component_key_for_tag(self) -> None:
        for case in self.cases["label_component_key_for_tag"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    label_component_key_for_tag(case["tag"]),
                )

    @patch("sysmon_tray.tray_darwin.subprocess.Popen")
    def test_launch_activity_monitor(self, mock_popen: MagicMock) -> None:
        from ..tray_darwin import _launch_activity_monitor

        _launch_activity_monitor()

        mock_popen.assert_called_once_with(
            ["open", "-a", ACTIVITY_MONITOR_APP_PATH],
            start_new_session=True,
        )

    def test_status_item_click_action(self) -> None:
        for case in self.cases["status_item_click_action"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    status_item_click_action(
                        case["click_count"],
                        case.get("button_number", 0),
                    ),
                )

    def test_status_item_delegate_status_bar_button_clicked(self) -> None:
        for case in self.cases["status_item_delegate_status_bar_button_clicked"]:
            with self.subTest(name=case["name"]):
                status_item = MagicMock()
                menu = MagicMock()
                with patch("sysmon_tray.tray_darwin.NSApp") as mock_ns_app, patch(
                    "sysmon_tray.tray_darwin.NSObject"
                ) as mock_nsobject, patch(
                    "sysmon_tray.tray_darwin._launch_activity_monitor",
                ) as mock_launch:
                    event = MagicMock()
                    event.clickCount.return_value = case["click_count"]
                    event.buttonNumber.return_value = case.get("button_number", 0)
                    mock_ns_app.currentEvent.return_value = event
                    delegate = _StatusItemDelegate.alloc().initWithCallbacks_(
                        _delegate_callbacks(
                            status_item=status_item,
                            menu=menu,
                        ),
                    )

                    delegate.statusBarButtonClicked_(None)

                    if case["expected"] == "activity_monitor":
                        mock_launch.assert_called_once_with()
                        mock_nsobject.cancelPreviousPerformRequestsWithTarget_selector_object_.assert_called()
                        status_item.popUpStatusItemMenu_.assert_not_called()
                    elif case["expected"] == "menu_delayed":
                        mock_launch.assert_not_called()
                        mock_nsobject.cancelPreviousPerformRequestsWithTarget_selector_object_.assert_called()
                        status_item.popUpStatusItemMenu_.assert_not_called()
                    else:
                        mock_launch.assert_not_called()
                        status_item.popUpStatusItemMenu_.assert_called_once_with(menu)

    def test_status_item_delegate_quit_app(self) -> None:
        on_quit = MagicMock()
        delegate = _StatusItemDelegate.alloc().initWithCallbacks_(
            _delegate_callbacks(on_quit=on_quit),
        )

        delegate.quitApp_(None)

        on_quit.assert_called_once_with()

    def test_status_item_delegate_set_refresh_interval(self) -> None:
        for case in self.cases["status_item_delegate_set_refresh_interval"]:
            with self.subTest(name=case["name"]):
                on_set_refresh = MagicMock()
                delegate = _StatusItemDelegate.alloc().initWithCallbacks_(
                    _delegate_callbacks(on_set_refresh=on_set_refresh),
                )
                sender = MagicMock()
                sender.tag.return_value = case["tag_ms"]

                delegate.setRefreshInterval_(sender)

                on_set_refresh.assert_called_once_with(case["expected_seconds"])

    def test_status_item_delegate_toggle_component(self) -> None:
        for case in self.cases["status_item_delegate_toggle_component"]:
            with self.subTest(name=case["name"]):
                on_toggle_component = MagicMock()
                delegate = _StatusItemDelegate.alloc().initWithCallbacks_(
                    _delegate_callbacks(on_toggle_component=on_toggle_component),
                )
                sender = MagicMock()
                sender.tag.return_value = case["tag"]

                delegate.toggleComponent_(sender)

                on_toggle_component.assert_called_once_with(case["expected_key"])


if __name__ == "__main__":
    unittest.main()
