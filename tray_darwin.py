"""Native macOS menu bar label via NSStatusItem."""

from __future__ import annotations

import sys
from typing import Callable

if sys.platform != "darwin":
    raise ImportError("tray_darwin is only available on macOS")

import objc
from AppKit import (
    NSApp,
    NSApplicationActivationPolicyAccessory,
    NSFont,
    NSMenu,
    NSMenuItem,
    NSStatusBar,
    NSVariableStatusItemLength,
)
from Foundation import NSObject

from .tray_common import (
    REFRESH_INTERVAL_SECONDS,
    format_refresh_interval_label,
    seconds_to_milliseconds,
)

__all__ = [
    "DarwinMenuBarLabel",
    "REFRESH_INTERVAL_SECONDS",
    "configure_ns_application",
    "format_refresh_interval_label",
    "seconds_to_milliseconds",
]


def configure_ns_application() -> None:
    """Register NSApplication as a menu-bar-only accessory app.

    PySide6 owns the event loop, but NSStatusItem still needs NSApp configured
    with the accessory activation policy or the status item may not appear.
    """
    NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)


class _StatusItemDelegate(NSObject):
    """Forward NSStatusItem actions to Python callbacks."""

    def initWithCallbacks_(self, callbacks):
        self = objc.super(_StatusItemDelegate, self).init()
        if self is None:
            return None
        self._on_set_refresh = callbacks["on_set_refresh"]
        return self

    def setRefreshInterval_(self, sender) -> None:
        self._on_set_refresh(sender.tag() / 1000.0)


class DarwinMenuBarLabel:
    """Menu bar text label backed by NSStatusItem."""

    def __init__(
        self,
        on_set_refresh: Callable[[float], None],
        refresh_seconds: float,
    ) -> None:
        configure_ns_application()
        self._status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength,
        )
        button = self._status_item.button()
        button.setFont_(
            NSFont.monospacedDigitSystemFontOfSize_weight_(13.0, 0.4),
        )
        button.setTitle_("-- | --C | -- | --C | --W | --W | --+ | --+")

        delegate = _StatusItemDelegate.alloc().initWithCallbacks_(
            {
                "on_set_refresh": on_set_refresh,
            },
        )
        self._delegate = delegate
        self._refresh_items: dict[float, NSMenuItem] = {}

        menu = NSMenu.alloc().init()

        interval_menu = NSMenu.alloc().init()
        interval_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Refresh interval",
            None,
            "",
        )
        interval_item.setSubmenu_(interval_menu)
        menu.addItem_(interval_item)

        for seconds in REFRESH_INTERVAL_SECONDS:
            option = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                format_refresh_interval_label(seconds, selected=seconds == refresh_seconds),
                "setRefreshInterval:",
                "",
            )
            option.setTarget_(delegate)
            option.setTag_(seconds_to_milliseconds(seconds))
            interval_menu.addItem_(option)
            self._refresh_items[seconds] = option

        menu.addItem_(NSMenuItem.separatorItem())
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit",
            "terminate:",
            "",
        )
        quit_item.setTarget_(NSApp)
        menu.addItem_(quit_item)
        self._status_item.setMenu_(menu)

    def set_refresh_interval(self, refresh_seconds: float) -> None:
        """Update the checked refresh interval in the menu."""
        for seconds, item in self._refresh_items.items():
            item.setTitle_(
                format_refresh_interval_label(seconds, selected=seconds == refresh_seconds),
            )

    def set_label(self, text: str) -> None:
        """Update the menu bar label text."""
        self._status_item.button().setTitle_(text)

    def set_tooltip(self, text: str) -> None:
        """Update the menu bar item tooltip."""
        self._status_item.button().setToolTip_(text)

    def show(self) -> None:
        """Ensure the status item is visible."""
        self._status_item.setVisible_(True)

    def hide(self) -> None:
        """Hide the status item."""
        self._status_item.setVisible_(False)
