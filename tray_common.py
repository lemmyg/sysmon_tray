"""Shared helpers for menu bar tray backends."""

from __future__ import annotations

REFRESH_INTERVAL_SECONDS: tuple[float, ...] = (0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 30.0)
STATUS_ITEM_TITLE_PADDING = 16.0
ABOUT_APP_NAME = "sysmon_tray"
ABOUT_MESSAGE_LINES: tuple[str, ...] = (
    "Minimalist MacOS system stats widget by lemmyg.",
    "MIT License.",
)
ABOUT_MENU_TEXT_WIDTH = 280.0

# (key, menu title) for each tray label segment.
LABEL_COMPONENTS: tuple[tuple[str, str], ...] = (
    ("cpu_util", "CPU %"),
    ("cpu_temp", "CPU °C"),
    ("gpu_util", "GPU %"),
    ("gpu_temp", "GPU °C"),
    ("memory", "Memory GB"),
    ("memory_pct", "Memory %"),
    ("disk", "Disk GB"),
    ("disk_pct", "Disk %"),
    ("system_power", "System power W"),
    ("battery_power", "Battery power W"),
    ("battery_pct", "Battery charge %"),
    ("fans", "Fans"),
)


def gpu_component_key(index: int, kind: str) -> str:
    """Return the component key for one GPU metric.

    Args:
        index (int): Zero-based GPU index.
        kind (str): ``util`` or ``temp``.

    Returns:
        str: Key like ``gpu0_util`` or ``gpu1_temp``.
    """
    return f"gpu{index}_{kind}"


def gpu_component_title(index: int, kind: str) -> str:
    """Return the Components menu title for one GPU metric.

    Args:
        index (int): Zero-based GPU index.
        kind (str): ``util`` or ``temp``.

    Returns:
        str: Title like ``GPU0 %`` or ``GPU1 °C``.
    """
    if kind == "util":
        return f"GPU{index} %"
    return f"GPU{index} °C"


def is_gpu_component_key(key: str) -> bool:
    """Return whether a component key is a per-GPU util or temp flag.

    Args:
        key (str): Component key.

    Returns:
        bool: True for keys like ``gpu0_util`` or ``gpu1_temp``.
    """
    if not key.startswith("gpu") or "_" not in key:
        return False
    prefix, kind = key.split("_", 1)
    if kind not in {"util", "temp"}:
        return False
    index_text = prefix[3:]
    return bool(index_text) and index_text.isdigit()


def label_components_for_gpu_count(
    gpu_count: int,
) -> tuple[tuple[str, str], ...]:
    """Return Components menu entries for the detected GPU count.

    One GPU keeps ``GPU %`` / ``GPU °C``. Two or more GPUs replace those
    with ``GPU0`` / ``GPU1`` util and temp items.

    Args:
        gpu_count (int): Number of detected GPUs.

    Returns:
        tuple[tuple[str, str], ...]: Component key and menu title pairs.
    """
    entries: list[tuple[str, str]] = []
    for key, title in LABEL_COMPONENTS:
        if key == "gpu_util" and gpu_count > 1:
            for index in range(gpu_count):
                entries.append(
                    (gpu_component_key(index, "util"), gpu_component_title(index, "util"))
                )
                entries.append(
                    (gpu_component_key(index, "temp"), gpu_component_title(index, "temp"))
                )
            continue
        if key == "gpu_temp" and gpu_count > 1:
            continue
        entries.append((key, title))
    return tuple(entries)


def ensure_gpu_component_defaults(
    components: dict[str, bool],
    gpu_count: int,
) -> dict[str, bool]:
    """Add missing per-GPU flags, inheriting from ``gpu_util`` / ``gpu_temp``.

    Args:
        components (dict[str, bool]): Current enabled map.
        gpu_count (int): Number of detected GPUs.

    Returns:
        dict[str, bool]: Copy with ``gpu0_*`` / ``gpu1_*`` defaults filled in.
    """
    updated = dict(components)
    if gpu_count <= 1:
        return updated
    for index in range(gpu_count):
        for kind in ("util", "temp"):
            key = gpu_component_key(index, kind)
            if key not in updated:
                updated[key] = is_label_component_enabled(updated, f"gpu_{kind}")
    return updated


def is_gpu_metric_enabled(
    components: dict[str, bool],
    index: int,
    kind: str,
    gpu_count: int,
) -> bool:
    """Return whether one GPU util or temp metric should appear.

    Args:
        components (dict[str, bool]): Current enabled map.
        index (int): Zero-based GPU index.
        kind (str): ``util`` or ``temp``.
        gpu_count (int): Number of detected GPUs.

    Returns:
        bool: Per-GPU flag when present, otherwise the shared GPU flag.
    """
    if gpu_count > 1:
        key = gpu_component_key(index, kind)
        if key in components:
            return bool(components[key])
    return is_label_component_enabled(components, f"gpu_{kind}")


def persistable_component_keys(components: dict[str, bool]) -> list[str]:
    """Return component keys that should be written to the config file.

    Args:
        components (dict[str, bool]): Current enabled map.

    Returns:
        list[str]: Shared LABEL_COMPONENTS keys plus any per-GPU keys.
    """
    keys = [key for key, _title in LABEL_COMPONENTS]
    extras = sorted(
        key for key in components if is_gpu_component_key(key) and key not in keys
    )
    return keys + extras


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


def format_about_text(
    app_name: str = ABOUT_APP_NAME,
    message_lines: tuple[str, ...] = ABOUT_MESSAGE_LINES,
) -> str:
    """Build the About submenu text block.

    Args:
        app_name (str): Application name shown first.
        message_lines (tuple[str, ...]): Remaining About text lines.

    Returns:
        str: Multi-line About text shown as one block.
    """
    return "\n".join((app_name, *message_lines))


def format_refresh_interval_label(seconds: float) -> str:
    """Build a menu label for a refresh interval option.

    Args:
        seconds (float): Polling interval in seconds.

    Returns:
        str: Menu text like ``2s`` or ``0.5s``.
    """
    if seconds == int(seconds):
        return f"{int(seconds)}s"
    return f"{seconds:g}s"


def seconds_to_milliseconds(seconds: float) -> int:
    """Convert a refresh interval in seconds to whole milliseconds.

    Args:
        seconds (float): Polling interval in seconds.

    Returns:
        int: Timer interval in milliseconds.
    """
    return int(seconds * 1000)
