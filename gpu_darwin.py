"""Read GPU device utilization from IOAccelerator on macOS."""

from __future__ import annotations

import ctypes
import sys
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

DEVICE_UTILIZATION_KEYS = (
    "Device Utilization %",
    "Device Utilization % at cur p-state",
)


def device_utilization_from_performance_statistics(
    stats: dict[str, object],
) -> Optional[float]:
    """Extract GPU utilization percent from IOAccelerator stats.

    Intel Macs publish utilization under ``PerformanceStatistics`` on
    ``IOAccelerator`` services. Apple Silicon typically exposes the same
    ``Device Utilization %`` key via darwin-perf / IOReport instead.

    Args:
        stats (dict[str, object]): ``PerformanceStatistics`` dictionary.

    Returns:
        float | None: Utilization from 0 to 100, or None when missing.
    """
    for key in DEVICE_UTILIZATION_KEYS:
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


def read_device_utilization_pct() -> Optional[float]:
    """Read current GPU device utilization from IOAccelerator.

    Returns:
        float | None: Utilization percent, or None when unavailable.
    """
    iterator = ctypes.c_uint32(0)
    result = IOServiceGetMatchingServices(
        0,
        IOServiceMatching(b"IOAccelerator"),
        ctypes.byref(iterator),
    )
    if result != 0:
        return None

    best: Optional[float] = None
    while True:
        service = IOIteratorNext(iterator.value)
        if not service:
            break
        stats = _read_registry_object(service, "PerformanceStatistics")
        if not stats:
            continue
        value = device_utilization_from_performance_statistics(stats)
        if value is None:
            continue
        if best is None or value > best:
            best = value
    return best


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
