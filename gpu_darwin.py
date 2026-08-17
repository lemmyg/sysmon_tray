"""Read GPU device utilization from IOAccelerator on macOS."""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass
from typing import Optional

if sys.platform != "darwin":
    raise ImportError("gpu_darwin is only available on macOS")

import objc

IOKit = ctypes.CDLL("/System/Library/Frameworks/IOKit.framework/IOKit")
CoreFoundation = ctypes.CDLL(
    "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation",
)

kCFAllocatorDefault = None

IOServiceMatching = IOKit.IOServiceMatching
IOServiceMatching.restype = ctypes.c_void_p
IOServiceGetMatchingServices = IOKit.IOServiceGetMatchingServices
IOServiceGetMatchingServices.restype = ctypes.c_int
IOServiceGetMatchingServices.argtypes = [
    ctypes.c_uint32,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_uint32),
]
IOIteratorNext = IOKit.IOIteratorNext
IORegistryEntryCreateCFProperty = IOKit.IORegistryEntryCreateCFProperty
IORegistryEntryCreateCFProperty.restype = ctypes.c_void_p
IORegistryEntryCreateCFProperty.argtypes = [
    ctypes.c_uint32,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_uint32,
]
CFStringCreateWithCString = CoreFoundation.CFStringCreateWithCString
CFStringCreateWithCString.restype = ctypes.c_void_p
CFStringCreateWithCString.argtypes = [
    ctypes.c_void_p,
    ctypes.c_char_p,
    ctypes.c_uint32,
]
CFRelease = CoreFoundation.CFRelease
CFRelease.argtypes = [ctypes.c_void_p]
IORegistryEntryGetParentEntry = IOKit.IORegistryEntryGetParentEntry
IORegistryEntryGetParentEntry.restype = ctypes.c_int
IORegistryEntryGetParentEntry.argtypes = [
    ctypes.c_uint32,
    ctypes.c_char_p,
    ctypes.POINTER(ctypes.c_uint32),
]
IOObjectGetClass = IOKit.IOObjectGetClass
IOObjectGetClass.restype = ctypes.c_int
IOObjectGetClass.argtypes = [ctypes.c_uint32, ctypes.c_char_p]
IOObjectRelease = IOKit.IOObjectRelease
IOObjectRelease.argtypes = [ctypes.c_uint32]

DEVICE_UTILIZATION_KEYS = (
    "Device Utilization %",
    "Device Utilization % at cur p-state",
    "GPU Activity(%)",
    "GPU Core Utilization",
)


@dataclass(frozen=True)
class GpuDevice:
    """One IOAccelerator GPU with a display name and optional utilization."""

    name: str
    util_pct: Optional[float]


def device_utilization_from_performance_statistics(
    stats: dict[str, object],
) -> Optional[float]:
    """Extract GPU utilization percent from IOAccelerator stats.

    Intel Macs publish utilization under ``PerformanceStatistics`` on
    ``IOAccelerator`` services. AMD dGPUs often leave ``Device Utilization %``
    at 0 and report load as ``GPU Activity(%)`` once the GPU is awake.
    Apple Silicon typically exposes ``Device Utilization %`` via darwin-perf.

    Args:
        stats (dict[str, object]): ``PerformanceStatistics`` dictionary.

    Returns:
        float | None: Utilization from 0 to 100, or None when missing.
    """
    device = _optional_float(stats.get("Device Utilization %"))
    activity = _optional_float(stats.get("GPU Activity(%)"))
    if device is not None and activity is not None:
        # AMD dGPUs often leave Device Utilization % at 0 and put the real
        # load in GPU Activity(%). Intel only publishes Device Utilization %.
        return max(device, activity)
    if device is not None:
        return device
    if activity is not None:
        return activity

    for key in DEVICE_UTILIZATION_KEYS:
        if key in {"Device Utilization %", "GPU Activity(%)"}:
            continue
        value = _optional_float(stats.get(key))
        if value is not None:
            return value

    unit_values: list[float] = []
    for key, raw in stats.items():
        if not str(key).startswith("Device Unit ") or not str(key).endswith(
            " Utilization %"
        ):
            continue
        value = _optional_float(raw)
        if value is not None:
            unit_values.append(value)
    if not unit_values:
        return None
    return max(unit_values)


def decode_registry_model(value: object) -> Optional[str]:
    """Decode an IORegistry model property into a GPU name.

    PCI ``model`` values are often CFData / bytes with a trailing NUL.

    Args:
        value (object): Raw registry value (bytes, CFData, or string).

    Returns:
        str | None: UTF-8 name, or None when empty.
    """
    if value is None:
        return None
    raw: Optional[bytes] = None
    if isinstance(value, bytes):
        raw = value
    else:
        try:
            raw = bytes(value)
        except (TypeError, ValueError):
            raw = None
    if raw is not None:
        text = raw.split(b"\x00", 1)[0].decode("utf-8", errors="ignore").strip()
        return text or None
    text = str(value).strip()
    if not text or text.startswith("{length"):
        return None
    return text


def gpu_display_name(io_class: Optional[str], model: Optional[str]) -> str:
    """Pick a short GPU label from a model string or IOClass.

    Args:
        io_class (str | None): IOAccelerator class name.
        model (str | None): PCI ``model`` string when available.

    Returns:
        str: Human-readable name such as ``Intel UHD Graphics 630``.
    """
    if model:
        return model
    lowered = (io_class or "").lower()
    if "intel" in lowered:
        return "Intel"
    if "amd" in lowered or "radeon" in lowered:
        return "AMD"
    if "nvidia" in lowered or "geforce" in lowered or "nvda" in lowered:
        return "NVIDIA"
    return "GPU"


def is_gpu_accelerator(io_class: Optional[str]) -> bool:
    """Return whether an IOKit class is a real GPU accelerator.

    ``IOAccelerator`` matching can include user clients and other children
    that are not GPUs.

    Args:
        io_class (str | None): IOKit class name.

    Returns:
        bool: True for classes like ``IntelAccelerator`` or ``AGXAcceleratorG17X``.
    """
    lowered = (io_class or "").lower()
    if not lowered or "userclient" in lowered:
        return False
    return "accelerator" in lowered


def unique_gpu_devices(devices: list[GpuDevice]) -> list[GpuDevice]:
    """Keep one device per GPU name, preferring a utilization reading.

    Args:
        devices (list[GpuDevice]): Possibly duplicated IOAccelerator devices.

    Returns:
        list[GpuDevice]: Unique GPUs, Intel first when present.
    """
    by_name: dict[str, GpuDevice] = {}
    for device in devices:
        existing = by_name.get(device.name)
        if existing is None or (
            existing.util_pct is None and device.util_pct is not None
        ):
            by_name[device.name] = device
    return sort_gpu_devices(list(by_name.values()))


def sort_gpu_devices(devices: list[GpuDevice]) -> list[GpuDevice]:
    """Sort GPUs so Intel integrated comes before discrete AMD/NVIDIA.

    SMC keys ``TG0*`` / ``TG1*`` follow that order on Intel Macs.

    Args:
        devices (list[GpuDevice]): Unordered IOAccelerator devices.

    Returns:
        list[GpuDevice]: Devices ordered for pairing with SMC temperatures.
    """
    return sorted(devices, key=lambda device: (_gpu_vendor_rank(device.name), device.name))


def read_gpu_devices() -> list[GpuDevice]:
    """Read each available IOAccelerator GPU name and utilization.

    User clients and duplicate names are omitted so one physical GPU is
    listed once.

    Returns:
        list[GpuDevice]: Detected GPUs, Intel first when present.
    """
    iterator = ctypes.c_uint32(0)
    result = IOServiceGetMatchingServices(
        0,
        IOServiceMatching(b"IOAccelerator"),
        ctypes.byref(iterator),
    )
    if result != 0:
        return []

    devices: list[GpuDevice] = []
    try:
        while True:
            service = IOIteratorNext(iterator.value)
            if not service:
                break
            io_class = _read_registry_string(service, "IOClass") or _object_class_name(
                service
            )
            if not is_gpu_accelerator(io_class):
                continue
            model = _read_registry_string(service, "model") or _parent_model(service)
            stats = _read_registry_object(service, "PerformanceStatistics") or {}
            devices.append(
                GpuDevice(
                    name=gpu_display_name(io_class, model),
                    util_pct=device_utilization_from_performance_statistics(stats),
                )
            )
    finally:
        IOObjectRelease(iterator.value)
    return unique_gpu_devices(devices)


def read_device_utilization_pct() -> Optional[float]:
    """Read the highest GPU device utilization from IOAccelerator.

    Returns:
        float | None: Utilization percent, or None when unavailable.
    """
    values = [
        device.util_pct
        for device in read_gpu_devices()
        if device.util_pct is not None
    ]
    if not values:
        return None
    return max(values)


def _gpu_vendor_rank(name: str) -> int:
    """Return a sort rank so Intel iGPU stays before discrete GPUs."""
    lowered = name.lower()
    if "intel" in lowered:
        return 0
    if "amd" in lowered or "radeon" in lowered:
        return 1
    if "nvidia" in lowered or "geforce" in lowered:
        return 2
    return 3


def _object_class_name(service: int) -> Optional[str]:
    """Read the IOKit class name for a registry entry."""
    buffer = ctypes.create_string_buffer(128)
    if IOObjectGetClass(service, buffer) != 0:
        return None
    return buffer.value.decode() or None


def _parent_model(service: int) -> Optional[str]:
    """Walk IOService parents until a PCI ``model`` name is found."""
    current = service
    for _depth in range(6):
        parent = ctypes.c_uint32(0)
        result = IORegistryEntryGetParentEntry(
            current,
            b"IOService",
            ctypes.byref(parent),
        )
        if current != service:
            IOObjectRelease(current)
        if result != 0:
            return None
        model = _read_registry_string(parent.value, "model")
        if model:
            IOObjectRelease(parent.value)
            return model
        current = parent.value
    if current != service:
        IOObjectRelease(current)
    return None


def _read_registry_string(service: int, property_name: str) -> Optional[str]:
    """Read one IORegistry property as a decoded string."""
    key = _cf_string(property_name)
    if not key:
        return None

    property_ref = IORegistryEntryCreateCFProperty(
        service,
        key,
        kCFAllocatorDefault,
        0,
    )
    CFRelease(key)
    if not property_ref:
        return None

    try:
        value = objc.objc_object(c_void_p=property_ref)
        return decode_registry_model(value)
    finally:
        CFRelease(property_ref)


def _cf_string(name: str) -> Optional[int]:
    """Create a CFString for an IORegistry property name."""
    value = CFStringCreateWithCString(
        kCFAllocatorDefault,
        name.encode(),
        0x08000100,
    )
    return value or None


def _read_registry_object(service: int, property_name: str) -> Optional[dict]:
    """Read one IORegistry property as a Python dictionary."""
    key = _cf_string(property_name)
    if not key:
        return None

    property_ref = IORegistryEntryCreateCFProperty(
        service,
        key,
        kCFAllocatorDefault,
        0,
    )
    CFRelease(key)
    if not property_ref:
        return None

    try:
        value = objc.objc_object(c_void_p=property_ref)
        if hasattr(value, "get"):
            return dict(value)
        return None
    finally:
        CFRelease(property_ref)


def _optional_float(value: object) -> Optional[float]:
    """Convert a value to float when it is numeric."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
