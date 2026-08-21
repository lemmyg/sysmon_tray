"""Read Mac model, chip, core counts, and disk identity for the tray tooltip."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional

if sys.platform != "darwin":
    raise ImportError("hardware_darwin is only available on macOS")

_cached_hardware_info: Optional["HardwareInfo"] = None
_hardware_info_loaded = False


@dataclass(frozen=True)
class GpuHardware:
    """Static GPU name and shader-core count from System Profiler."""

    name: str
    core_count: int


@dataclass(frozen=True)
class DiskHardware:
    """Static internal drive name, medium, and capacity."""

    name: Optional[str] = None
    medium: Optional[str] = None
    size_bytes: Optional[int] = None


@dataclass(frozen=True)
class HardwareInfo:
    """Static machine identity used in the tray tooltip header."""

    machine_model: Optional[str] = None
    chip_name: Optional[str] = None
    cpu_cores: Optional[int] = None
    gpus: list[GpuHardware] = field(default_factory=list)
    disk: Optional[DiskHardware] = None


def optional_stripped_text(value: object) -> Optional[str]:
    """Return a stripped string when the value is a non-empty string.

    Args:
        value (object): Raw profiler field.

    Returns:
        str | None: Stripped text, or None when missing or blank.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def optional_positive_int(value: object) -> Optional[int]:
    """Parse a positive integer from a profiler field.

    Args:
        value (object): Raw integer or decimal string.

    Returns:
        int | None: Parsed value when greater than zero.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    text = optional_stripped_text(value)
    if text is None or not text.isdigit():
        return None
    number = int(text)
    return number if number > 0 else None


def machine_model_from_overview(overview: dict) -> Optional[str]:
    """Build a laptop model label from a hardware overview dictionary.

    Args:
        overview (dict): One ``SPHardwareDataType`` entry.

    Returns:
        str | None: Marketing name with identifier, or None when both are
            missing.
    """
    name = optional_stripped_text(overview.get("machine_name"))
    ident = optional_stripped_text(overview.get("machine_model"))
    if name and ident:
        return f"{name} ({ident})"
    return name or ident


def chip_name_from_overview(overview: dict) -> Optional[str]:
    """Read the SoC or CPU marketing name from a hardware overview.

    Args:
        overview (dict): One ``SPHardwareDataType`` entry.

    Returns:
        str | None: Chip label such as ``Apple M5 Max``.
    """
    return optional_stripped_text(
        overview.get("chip_type")
    ) or optional_stripped_text(overview.get("cpu_type"))


def cpu_cores_from_number_processors(value: object) -> Optional[int]:
    """Parse total CPU cores from a System Profiler ``number_processors`` field.

    Apple Silicon values look like ``proc 18:6:0:12`` (total first). Intel
    values look like ``proc 8:16`` (cores then threads).

    Args:
        value (object): Raw ``number_processors`` field.

    Returns:
        int | None: Total CPU core count when parseable.
    """
    direct = optional_positive_int(value)
    if direct is not None:
        return direct
    text = optional_stripped_text(value)
    if text is None:
        return None
    lowered = text.lower()
    if lowered.startswith("proc"):
        text = text[4:].strip()
    first = text.split(":", 1)[0].strip().split()[0]
    return optional_positive_int(first)


def is_profiler_yes(value: object) -> bool:
    """Return True when a profiler flag is ``yes``.

    Args:
        value (object): Raw yes/no profiler field.

    Returns:
        bool: True when the value is yes.
    """
    text = optional_stripped_text(value)
    return text is not None and text.lower() == "yes"


def is_profiler_no(value: object) -> bool:
    """Return True when a profiler flag is ``no``.

    Args:
        value (object): Raw yes/no profiler field.

    Returns:
        bool: True when the value is no.
    """
    text = optional_stripped_text(value)
    return text is not None and text.lower() == "no"


def flatten_profiler_items(entries: object) -> list[dict]:
    """Flatten nested System Profiler ``_items`` lists.

    Args:
        entries (object): Profiler controller list.

    Returns:
        list[dict]: Leaf device dictionaries.
    """
    if not isinstance(entries, list):
        return []
    items: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        nested = entry.get("_items")
        if isinstance(nested, list) and nested:
            items.extend(flatten_profiler_items(nested))
        else:
            items.append(entry)
    return items


def disk_medium_label(medium_type: Optional[str]) -> Optional[str]:
    """Normalize a profiler medium type to SSD or HDD.

    Args:
        medium_type (str | None): Raw ``medium_type`` value.

    Returns:
        str | None: ``SSD`` or ``HDD`` when recognized.
    """
    text = optional_stripped_text(medium_type)
    if text is None:
        return None
    return {
        "ssd": "SSD",
        "hdd": "HDD",
        "rotational": "HDD",
        "fusion": "Fusion",
    }.get(text.lower(), text.upper())


def disk_from_controller_entry(entry: dict) -> Optional[DiskHardware]:
    """Build disk identity from an NVMe or SATA device entry.

    Args:
        entry (dict): One flattened controller device.

    Returns:
        DiskHardware | None: Internal disk when present.
    """
    if is_profiler_yes(entry.get("detachable_drive")):
        return None
    if is_profiler_yes(entry.get("removable_media")):
        return None
    name = optional_stripped_text(
        entry.get("device_model")
    ) or optional_stripped_text(entry.get("_name"))
    size_bytes = optional_positive_int(entry.get("size_in_bytes"))
    if name is None and size_bytes is None:
        return None
    return DiskHardware(name=name, size_bytes=size_bytes)


def disk_from_storage_entry(entry: dict) -> Optional[DiskHardware]:
    """Build disk identity from a mounted storage volume.

    Args:
        entry (dict): One ``SPStorageDataType`` volume.

    Returns:
        DiskHardware | None: Internal disk when present.
    """
    drive = entry.get("physical_drive")
    if not isinstance(drive, dict):
        return None
    if is_profiler_no(drive.get("is_internal_disk")):
        return None
    name = optional_stripped_text(drive.get("device_name"))
    medium = disk_medium_label(optional_stripped_text(drive.get("medium_type")))
    size_bytes = optional_positive_int(entry.get("size_in_bytes"))
    if name is None and medium is None and size_bytes is None:
        return None
    return DiskHardware(name=name, medium=medium, size_bytes=size_bytes)


def merge_disk_hardware(
    left: Optional[DiskHardware],
    right: Optional[DiskHardware],
) -> Optional[DiskHardware]:
    """Fill missing disk fields from a second source.

    Args:
        left (DiskHardware | None): Preferred disk identity.
        right (DiskHardware | None): Fallback fields.

    Returns:
        DiskHardware | None: Combined identity, or None when both are missing.
    """
    if left is None:
        return right
    if right is None:
        return left
    return DiskHardware(
        name=left.name or right.name,
        medium=left.medium or right.medium,
        size_bytes=left.size_bytes or right.size_bytes,
    )


def disk_hardware_from_controllers(entries: object) -> Optional[DiskHardware]:
    """Return the first internal disk from NVMe or SATA controllers.

    Args:
        entries (object): ``SPNVMeDataType`` or ``SPSerialATADataType``.

    Returns:
        DiskHardware | None: First internal disk.
    """
    for entry in flatten_profiler_items(entries):
        disk = disk_from_controller_entry(entry)
        if disk is not None:
            return disk
    return None


def disk_hardware_from_storage(entries: object) -> Optional[DiskHardware]:
    """Return the internal root volume disk from storage profiler data.

    Args:
        entries (object): ``SPStorageDataType`` list.

    Returns:
        DiskHardware | None: Disk for ``/``, or the first internal volume.
    """
    if not isinstance(entries, list):
        return None
    fallback: Optional[DiskHardware] = None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        disk = disk_from_storage_entry(entry)
        if disk is None:
            continue
        if optional_stripped_text(entry.get("mount_point")) == "/":
            return disk
        if fallback is None:
            fallback = disk
    return fallback


def disk_hardware_from_profiler_payload(payload: object) -> Optional[DiskHardware]:
    """Build internal disk identity from combined profiler JSON.

    Args:
        payload (object): Parsed ``system_profiler`` JSON object.

    Returns:
        DiskHardware | None: Internal SSD/HDD identity when present.
    """
    if not isinstance(payload, dict):
        return None
    disk = disk_hardware_from_controllers(payload.get("SPNVMeDataType"))
    disk = merge_disk_hardware(
        disk,
        disk_hardware_from_controllers(payload.get("SPSerialATADataType")),
    )
    return merge_disk_hardware(
        disk,
        disk_hardware_from_storage(payload.get("SPStorageDataType")),
    )


def gpu_hardware_from_displays(entries: object) -> list[GpuHardware]:
    """Parse GPU names and core counts from ``SPDisplaysDataType``.

    Args:
        entries (object): Profiler display/GPU list.

    Returns:
        list[GpuHardware]: GPUs that report a core count.
    """
    if not isinstance(entries, list):
        return []
    gpus: list[GpuHardware] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        cores = optional_positive_int(entry.get("sppci_cores"))
        if cores is None:
            continue
        name = optional_stripped_text(
            entry.get("sppci_model")
        ) or optional_stripped_text(entry.get("_name"))
        gpus.append(GpuHardware(name=name or "GPU", core_count=cores))
    return gpus


def hardware_overview_from_payload(payload: object) -> Optional[dict]:
    """Return the first hardware overview dictionary from profiler JSON.

    Args:
        payload (object): Parsed ``system_profiler`` JSON object.

    Returns:
        dict | None: First ``SPHardwareDataType`` entry when present.
    """
    if not isinstance(payload, dict):
        return None
    entries = payload.get("SPHardwareDataType")
    if not isinstance(entries, list) or not entries:
        return None
    overview = entries[0]
    if not isinstance(overview, dict):
        return None
    return overview


def hardware_info_from_profiler_payload(payload: object) -> HardwareInfo:
    """Build static hardware info from combined profiler JSON.

    Args:
        payload (object): Parsed ``SPHardwareDataType`` and
            ``SPDisplaysDataType`` JSON object.

    Returns:
        HardwareInfo: Model, chip, and core counts when present.
    """
    overview = hardware_overview_from_payload(payload)
    if overview is None:
        overview = {}
    displays = payload.get("SPDisplaysDataType") if isinstance(payload, dict) else None
    return HardwareInfo(
        machine_model=machine_model_from_overview(overview),
        chip_name=chip_name_from_overview(overview),
        cpu_cores=cpu_cores_from_number_processors(
            overview.get("number_processors")
        ),
        gpus=gpu_hardware_from_displays(displays),
        disk=disk_hardware_from_profiler_payload(payload),
    )


def read_hardware_info() -> HardwareInfo:
    """Read model, chip, and core counts from System Profiler.

    The result is cached because this hardware does not change at runtime.

    Returns:
        HardwareInfo: Static identity fields, empty when unavailable.
    """
    global _cached_hardware_info, _hardware_info_loaded
    if _hardware_info_loaded:
        return _cached_hardware_info or HardwareInfo()
    info = HardwareInfo()
    try:
        raw = subprocess.check_output(
            [
                "system_profiler",
                "SPHardwareDataType",
                "SPDisplaysDataType",
                "SPNVMeDataType",
                "SPSerialATADataType",
                "SPStorageDataType",
                "-json",
            ],
            stderr=subprocess.DEVNULL,
            timeout=12,
        )
        payload = json.loads(raw)
        info = hardware_info_from_profiler_payload(payload)
    except (
        OSError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ):
        info = HardwareInfo()
    _cached_hardware_info = info
    _hardware_info_loaded = True
    return info
