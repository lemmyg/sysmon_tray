"""Load and save user preferences for sysmon_tray."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

from .tray_common import LABEL_COMPONENTS, default_label_components

__all__ = [
    "default_config_path",
    "load_label_components",
    "merge_label_components",
    "save_label_components",
]


def default_config_path() -> Path:
    """Return the default user config file path.

    Returns:
        Path: ``~/Library/Application Support/sysmon_tray/config.yaml``.
    """
    return (
        Path.home()
        / "Library"
        / "Application Support"
        / "sysmon_tray"
        / "config.yaml"
    )


def merge_label_components(raw: Any) -> dict[str, bool]:
    """Merge saved component flags onto the defaults.

    Args:
        raw (Any): Value loaded from the config ``components`` key.

    Returns:
        dict[str, bool]: Complete enabled map for all known components.
    """
    components = default_label_components()
    if not isinstance(raw, dict):
        return components
    for key, _title in LABEL_COMPONENTS:
        if key in raw:
            components[key] = bool(raw[key])
    return components


def load_label_components(path: Optional[Path] = None) -> dict[str, bool]:
    """Load enabled tray components from the user config file.

    Args:
        path (Path | None): Config file path. When None, use default_config_path().

    Returns:
        dict[str, bool]: Enabled map. Missing or invalid files yield defaults.
    """
    config_path = default_config_path() if path is None else path
    if not config_path.is_file():
        return default_label_components()
    try:
        with config_path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError):
        return default_label_components()
    if not isinstance(data, dict):
        return default_label_components()
    return merge_label_components(data.get("components"))


def save_label_components(
    components: dict[str, bool],
    path: Optional[Path] = None,
) -> None:
    """Persist enabled tray components to the user config file.

    Args:
        components (dict[str, bool]): Component key to enabled flag.
        path (Path | None): Config file path. When None, use default_config_path().
    """
    config_path = default_config_path() if path is None else path
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    if config_path.is_file():
        try:
            with config_path.open(encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle)
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, yaml.YAMLError):
            data = {}
    data["components"] = {
        key: bool(components.get(key, True)) for key, _title in LABEL_COMPONENTS
    }
    with config_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, default_flow_style=False, sort_keys=False)
