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
    NSControlStateValueOff,
    NSControlStateValueOn,
    NSFont,
    NSLineBreakByTruncatingTail,
    NSMenu,
    NSMenuItem,
    NSStatusBar,
    NSVariableStatusItemLength,
)
from Foundation import NSObject

from .tray_common import (
    LABEL_COMPONENTS,
    REFRESH_INTERVAL_SECONDS,
    format_refresh_interval_label,
    is_label_component_enabled,
    label_component_key_for_tag,
    seconds_to_milliseconds,
    status_item_length_for_title_width,
)

__all__ = [
    "DarwinMenuBarLabel",
    "REFRESH_INTERVAL_SECONDS",
    "configure_ns_application",
    "format_refresh_interval_label",
    "seconds_to_milliseconds",
    "status_item_length_for_title_width",
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
        self._on_toggle_component = callbacks["on_toggle_component"]
        self._on_quit = callbacks["on_quit"]
        return self

    def setRefreshInterval_(self, sender) -> None:
        self._on_set_refresh(sender.tag() / 1000.0)

    def toggleComponent_(self, sender) -> None:
        self._on_toggle_component(label_component_key_for_tag(int(sender.tag())))

    def quitApp_(self, sender) -> None:
        self._on_quit()


class DarwinMenuBarLabel:
    """Menu bar text label backed by NSStatusItem."""

    def __init__(
        self,
        on_set_refresh: Callable[[float], None],
        on_toggle_component: Callable[[str], None],
        on_quit: Callable[[], None],
        refresh_seconds: float,
        components: dict[str, bool],
    ) -> None:
        configure_ns_application()
        self._status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength,
        )
        button = self._status_item.button()
        button.setFont_(
            NSFont.monospacedDigitSystemFontOfSize_weight_(12.0, 0.4),
        )
        button.setUsesSingleLineMode_(True)
        cell = button.cell()
        if cell is not None:
            cell.setWraps_(False)
            cell.setLineBreakMode_(NSLineBreakByTruncatingTail)
        button.setTitle_("-- --° -- --° --W --W --+ --+")
        self._sync_status_item_length()

        delegate = _StatusItemDelegate.alloc().initWithCallbacks_(
            {
                "on_set_refresh": on_set_refresh,
                "on_toggle_component": on_toggle_component,
                "on_quit": on_quit,
            },
        )
        self._delegate = delegate
        self._refresh_items: dict[float, NSMenuItem] = {}
        self._component_items: dict[str, NSMenuItem] = {}

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

        components_menu = NSMenu.alloc().init()
        components_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Components",
            None,
            "",
        )
        components_item.setSubmenu_(components_menu)
        menu.addItem_(components_item)

        for index, (key, title) in enumerate(LABEL_COMPONENTS):
            option = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title,
                "toggleComponent:",
                "",
            )
            option.setTarget_(delegate)
            option.setTag_(index)
            option.setState_(
                NSControlStateValueOn
                if is_label_component_enabled(components, key)
                else NSControlStateValueOff,
            )
            components_menu.addItem_(option)
            self._component_items[key] = option

        menu.addItem_(NSMenuItem.separatorItem())
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit",
            "quitApp:",
            "",
        )
        quit_item.setTarget_(delegate)
        menu.addItem_(quit_item)
        self._status_item.setMenu_(menu)

    def set_refresh_interval(self, refresh_seconds: float) -> None:
        """Update the checked refresh interval in the menu."""
        for seconds, item in self._refresh_items.items():
            item.setTitle_(
                format_refresh_interval_label(seconds, selected=seconds == refresh_seconds),
            )

    def set_components(self, components: dict[str, bool]) -> None:
        """Update checkmarks for enabled tray label components.

        Args:
            components (dict[str, bool]): Component key to enabled flag.
        """
        for key, item in self._component_items.items():
            item.setState_(
                NSControlStateValueOn
                if is_label_component_enabled(components, key)
                else NSControlStateValueOff,
            )

    def set_label(self, text: str) -> None:
        """Update the menu bar label text."""
        self._status_item.button().setTitle_(text)
        self._sync_status_item_length()

    def set_tooltip(self, text: str) -> None:
        """Update the menu bar item tooltip."""
        self._status_item.button().setToolTip_(text)

    def show(self) -> None:
        """Ensure the status item is visible."""
        self._status_item.setVisible_(True)

    def hide(self) -> None:
        """Hide the status item."""
        self._status_item.setVisible_(False)

    def _sync_status_item_length(self) -> None:
        """Resize the status item so the title does not overlap neighbors."""
        button = self._status_item.button()
        fitting_width = float(button.fittingSize().width)
        if fitting_width <= 0:
            self._status_item.setLength_(NSVariableStatusItemLength)
            return
        self._status_item.setLength_(
            status_item_length_for_title_width(fitting_width),
        )
