"""macOS menu bar monitor for CPU temperature and fan speed."""

__all__ = ["SensorSnapshot", "format_tooltip", "format_tray_label", "read_sensors"]

from .sensors import SensorSnapshot, format_tooltip, format_tray_label, read_sensors
