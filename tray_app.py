"""Qt menu bar application for live sensor monitoring on macOS."""

from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .config import load_label_components, save_label_components
from .sensors import format_tooltip, format_tray_label, read_sensors
from .tray_common import ensure_gpu_component_defaults, toggle_label_component
from .tray_darwin import DarwinMenuBarLabel, seconds_to_milliseconds


class TrayMonitorApp:
    """Manage the menu bar label and refresh timer."""

    def __init__(self, refresh_seconds: float = 5.0) -> None:
        self._refresh_seconds = refresh_seconds
        self._refresh_ms = seconds_to_milliseconds(refresh_seconds)
        self._components = load_label_components()
        self._app = QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)
        self._app.setApplicationName("sysmon_tray")

        self._darwin_label = DarwinMenuBarLabel(
            on_set_refresh=self.set_refresh_seconds,
            on_toggle_component=self.toggle_component,
            on_quit=self._app.quit,
            refresh_seconds=refresh_seconds,
            components=self._components,
        )

        self._timer = QTimer(self._app)
        self._timer.timeout.connect(self.refresh)

    def refresh(self) -> None:
        """Poll sensors and update the menu bar label."""
        snapshot = read_sensors()
        gpu_count = len(snapshot.gpus)
        self._components = ensure_gpu_component_defaults(self._components, gpu_count)
        self._darwin_label.set_components(self._components)
        self._darwin_label.set_gpu_count(gpu_count)
        label = format_tray_label(snapshot, self._components)
        tooltip = format_tooltip(snapshot)
        self._darwin_label.set_label(label)
        self._darwin_label.set_tooltip(tooltip)

    def toggle_component(self, key: str) -> None:
        """Enable or disable a tray label component and refresh the label.

        Args:
            key (str): Component key from LABEL_COMPONENTS.
        """
        self._components = toggle_label_component(self._components, key)
        save_label_components(self._components)
        self._darwin_label.set_components(self._components)
        self.refresh()

    def set_refresh_seconds(self, refresh_seconds: float) -> None:
        """Change the polling interval and restart the refresh timer.

        Args:
            refresh_seconds (float): New polling interval in seconds.
        """
        if refresh_seconds <= 0:
            return
        self._refresh_seconds = refresh_seconds
        self._refresh_ms = seconds_to_milliseconds(refresh_seconds)
        self._timer.stop()
        self._timer.start(self._refresh_ms)
        self._darwin_label.set_refresh_interval(refresh_seconds)

    def run(self) -> int:
        """Start the tray monitor event loop.

        Returns:
            int: Application exit code.
        """
        self.refresh()
        self._darwin_label.show()
        self._timer.start(self._refresh_ms)
        return self._app.exec()
