"""Native macOS menu bar label via NSStatusItem."""

from __future__ import annotations

import subprocess
import sys
from typing import Callable, Literal

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
    NSTextAlignmentCenter,
    NSTextField,
    NSEventMaskLeftMouseUp,
    NSEventMaskRightMouseUp,
    NSVariableStatusItemLength,
)
from Foundation import NSObject

from .tray_common import (
    ABOUT_MENU_TEXT_WIDTH,
    LABEL_COMPONENTS,
    REFRESH_INTERVAL_SECONDS,
    format_about_text,
    format_refresh_interval_label,
    is_label_component_enabled,
    label_component_key_for_tag,
    label_components_for_gpu_count,
    seconds_to_milliseconds,
    status_item_length_for_title_width,
)

__all__ = [
    "DarwinMenuBarLabel",
    "REFRESH_INTERVAL_SECONDS",
    "about_menu_text_field",
    "configure_ns_application",
    "format_about_text",
    "format_refresh_interval_label",
    "seconds_to_milliseconds",
    "status_item_length_for_title_width",
]

STATUS_ITEM_MENU_DELAY_SECONDS = 0.25
ACTIVITY_MONITOR_APP_PATH = "/System/Applications/Utilities/Activity Monitor.app"


def _launch_activity_monitor() -> None:
    """Open the macOS Activity Monitor application."""
    subprocess.Popen(
        ["open", "-a", ACTIVITY_MONITOR_APP_PATH],
        start_new_session=True,
    )


def status_item_click_action(
    click_count: int,
    button_number: int = 0,
) -> Literal["activity_monitor", "menu", "menu_delayed"]:
    """Resolve the action for a status item mouse click.

    Args:
        click_count (int): NSEvent click count for the current gesture.
        button_number (int): Mouse button number (0 for primary).

    Returns:
        Literal["activity_monitor", "menu", "menu_delayed"]: Action to perform
            for the click.
    """
    if click_count >= 2 and button_number == 0:
        return "activity_monitor"
    if click_count == 1 and button_number == 0:
        return "menu_delayed"
    return "menu"


def configure_ns_application() -> None:
    """Register NSApplication as a menu-bar-only accessory app.

    PySide6 owns the event loop, but NSStatusItem still needs NSApp configured
    with the accessory activation policy or the status item may not appear.
    """
    NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)


def about_menu_text_field(width: float = ABOUT_MENU_TEXT_WIDTH) -> NSTextField:
    """Build a single text field for the About submenu.

    Args:
        width (float): Preferred maximum layout width in points.

    Returns:
        NSTextField: Non-editable label with the About text block.
    """
    field = NSTextField.alloc().initWithFrame_(((0.0, 0.0), (float(width), 1.0)))
    field.setStringValue_(format_about_text())
    field.setBezeled_(False)
    field.setBordered_(False)
    field.setDrawsBackground_(False)
    field.setEditable_(False)
    field.setSelectable_(False)
    field.setAlignment_(NSTextAlignmentCenter)
    field.setFont_(NSFont.menuFontOfSize_(0.0))
    field.setPreferredMaxLayoutWidth_(float(width))
    cell = field.cell()
    if cell is not None:
        cell.setWraps_(True)
    fitting_size = field.fittingSize()
    field.setFrameSize_((float(width), float(fitting_size.height)))
    return field


class _StatusItemDelegate(NSObject):
    """Forward NSStatusItem actions to Python callbacks."""

    def initWithCallbacks_(self, callbacks):
        self = objc.super(_StatusItemDelegate, self).init()
        if self is None:
            return None
        self._on_set_refresh = callbacks["on_set_refresh"]
        self._on_toggle_component = callbacks["on_toggle_component"]
        self._on_quit = callbacks["on_quit"]
        self._status_item = callbacks["status_item"]
        self._menu = callbacks["menu"]
        self._component_keys = [key for key, _title in LABEL_COMPONENTS]
        return self

    def setRefreshInterval_(self, sender) -> None:
        self._on_set_refresh(sender.tag() / 1000.0)

    def toggleComponent_(self, sender) -> None:
        tag = int(sender.tag())
        if 0 <= tag < len(self._component_keys):
            self._on_toggle_component(self._component_keys[tag])
            return
        self._on_toggle_component(label_component_key_for_tag(tag))

    def quitApp_(self, sender) -> None:
        self._on_quit()

    def showStatusMenu_(self, sender) -> None:
        """Pop up the status item menu after a delayed single click."""
        self._status_item.popUpStatusItemMenu_(self._menu)

    def statusBarButtonClicked_(self, sender) -> None:
        """Show the menu or launch Activity Monitor on double-click."""
        event = NSApp.currentEvent()
        click_count = 0 if event is None else int(event.clickCount())
        button_number = 0 if event is None else int(event.buttonNumber())
        action = status_item_click_action(click_count, button_number)
        if action == "activity_monitor":
            NSObject.cancelPreviousPerformRequestsWithTarget_selector_object_(
                self,
                "showStatusMenu:",
                None,
            )
            _launch_activity_monitor()
            return
        if action == "menu_delayed":
            NSObject.cancelPreviousPerformRequestsWithTarget_selector_object_(
                self,
                "showStatusMenu:",
                None,
            )
            self.performSelector_withObject_afterDelay_(
                "showStatusMenu:",
                None,
                STATUS_ITEM_MENU_DELAY_SECONDS,
            )
            return
        self._status_item.popUpStatusItemMenu_(self._menu)


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
        button.setTitle_("C--%--° G--%--° M--G--% B--%--W S--W F--+ F--+")
        self._sync_status_item_length()

        self._refresh_items: dict[float, NSMenuItem] = {}
        self._component_items: dict[str, NSMenuItem] = {}
        self._components = dict(components)
        self._gpu_count = 1

        menu = NSMenu.alloc().init()

        interval_menu = NSMenu.alloc().init()
        interval_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Refresh interval",
            None,
            "",
        )
        interval_item.setSubmenu_(interval_menu)
        menu.addItem_(interval_item)

        delegate = _StatusItemDelegate.alloc().initWithCallbacks_(
            {
                "on_set_refresh": on_set_refresh,
                "on_toggle_component": on_toggle_component,
                "on_quit": on_quit,
                "status_item": self._status_item,
                "menu": menu,
            },
        )
        self._delegate = delegate

        for seconds in REFRESH_INTERVAL_SECONDS:
            option = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                format_refresh_interval_label(seconds),
                "setRefreshInterval:",
                "",
            )
            option.setTarget_(delegate)
            option.setTag_(seconds_to_milliseconds(seconds))
            option.setState_(
                NSControlStateValueOn
                if seconds == refresh_seconds
                else NSControlStateValueOff,
            )
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
        self._components_menu = components_menu
        self._fill_components_menu()

        menu.addItem_(NSMenuItem.separatorItem())
        about_menu = NSMenu.alloc().init()
        about_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "About",
            None,
            "",
        )
        about_item.setSubmenu_(about_menu)
        menu.addItem_(about_item)
        about_text_item = NSMenuItem.alloc().init()
        about_text_item.setView_(about_menu_text_field())
        about_menu.addItem_(about_text_item)
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit",
            "quitApp:",
            "",
        )
        quit_item.setTarget_(delegate)
        menu.addItem_(quit_item)

        button.setTarget_(delegate)
        button.setAction_("statusBarButtonClicked:")
        button.sendActionOn_(NSEventMaskLeftMouseUp | NSEventMaskRightMouseUp)

    def set_refresh_interval(self, refresh_seconds: float) -> None:
        """Update the checked refresh interval in the menu."""
        for seconds, item in self._refresh_items.items():
            item.setState_(
                NSControlStateValueOn
                if seconds == refresh_seconds
                else NSControlStateValueOff,
            )

    def set_components(self, components: dict[str, bool]) -> None:
        """Update checkmarks for enabled tray label components.

        Args:
            components (dict[str, bool]): Component key to enabled flag.
        """
        self._components = dict(components)
        for key, item in self._component_items.items():
            item.setState_(
                NSControlStateValueOn
                if is_label_component_enabled(self._components, key)
                else NSControlStateValueOff,
            )

    def set_gpu_count(self, gpu_count: int) -> None:
        """Rebuild the Components menu when the GPU count changes.

        Args:
            gpu_count (int): Number of detected GPUs.
        """
        count = max(1, int(gpu_count))
        if count == self._gpu_count:
            return
        self._gpu_count = count
        self._fill_components_menu()

    def _fill_components_menu(self) -> None:
        """Populate the Components submenu for the current GPU count."""
        self._components_menu.removeAllItems()
        self._component_items = {}
        entries = label_components_for_gpu_count(self._gpu_count)
        self._delegate._component_keys = [key for key, _title in entries]
        for index, (key, title) in enumerate(entries):
            option = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title,
                "toggleComponent:",
                "",
            )
            option.setTarget_(self._delegate)
            option.setTag_(index)
            option.setState_(
                NSControlStateValueOn
                if is_label_component_enabled(self._components, key)
                else NSControlStateValueOff,
            )
            self._components_menu.addItem_(option)
            self._component_items[key] = option

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
