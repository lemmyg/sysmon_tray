"""Shared helpers for menu bar tray backends."""

from __future__ import annotations

REFRESH_INTERVAL_SECONDS: tuple[float, ...] = (0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 30.0)
STATUS_ITEM_TITLE_PADDING = 16.0

# (key, menu title) for each tray label segment.
LABEL_COMPONENTS: tuple[tuple[str, str], ...] = (
    ("cpu_util", "CPU util"),
    ("cpu_temp", "CPU temp"),
    ("gpu_util", "GPU util"),
    ("gpu_temp", "GPU temp"),
    ("system_power", "System power"),
    ("battery_power", "Battery power"),
    ("battery_pct", "Battery %"),
    ("fans", "Fans"),
)


def default_label_components() -> dict[str, bool]:
    """Return the default enabled map for all tray label components.

    Returns:
        dict[str, bool]: Component key to enabled flag (all True).
    """
    return {key: True for key, _title in LABEL_COMPONENTS}


def is_label_component_enabled(components: dict[str, bool], key: str) -> bool:
    """Return whether a tray label component is enabled.

    Args:
        components (dict[str, bool]): Current enabled map.
        key (str): Component key from LABEL_COMPONENTS.

    Returns:
        bool: True when the component should appear in the label.
    """
    return bool(components.get(key, True))


def toggle_label_component(components: dict[str, bool], key: str) -> dict[str, bool]:
    """Return a copy of components with one key toggled.

    Args:
        components (dict[str, bool]): Current enabled map.
        key (str): Component key from LABEL_COMPONENTS.

    Returns:
        dict[str, bool]: Updated enabled map.
    """
    updated = dict(components)
    updated[key] = not is_label_component_enabled(updated, key)
    return updated


def label_component_key_for_tag(tag: int) -> str:
    """Map a menu item tag to a LABEL_COMPONENTS key.

    Args:
        tag (int): Zero-based index into LABEL_COMPONENTS.

    Returns:
        str: Component key for the tag.
    """
    return LABEL_COMPONENTS[tag][0]


def status_item_length_for_title_width(
    title_width: float,
    padding: float = STATUS_ITEM_TITLE_PADDING,
) -> float:
    """Compute NSStatusItem length from measured button fitting width.

    Args:
        title_width (float): Width from NSStatusBarButton.fittingSize in points.
        padding (float): Extra horizontal padding for menu bar chrome.

    Returns:
        float: Length to pass to NSStatusItem.setLength_.
    """
    return max(0.0, float(title_width)) + float(padding)


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
