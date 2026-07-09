"""Shared helpers for menu bar tray backends."""

from __future__ import annotations

REFRESH_INTERVAL_SECONDS: tuple[float, ...] = (0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 30.0)


def format_refresh_interval_label(seconds: float, *, selected: bool = False) -> str:
    """Build a menu label for a refresh interval option.

    Args:
        seconds (float): Polling interval in seconds.
        selected (bool): Whether this option is currently active.

    Returns:
        str: Menu text like ``2s`` or ``2s *``.
    """
    if seconds == int(seconds):
        label = f"{int(seconds)}s"
    else:
        label = f"{seconds:g}s"
    if selected:
        return f"{label} *"
    return label


def seconds_to_milliseconds(seconds: float) -> int:
    """Convert a refresh interval in seconds to whole milliseconds.

    Args:
        seconds (float): Polling interval in seconds.

    Returns:
        int: Timer interval in milliseconds.
    """
    return int(seconds * 1000)
