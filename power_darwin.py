"""Read total and battery power from AppleSmartBattery telemetry on macOS."""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass
from typing import Optional

if sys.platform != "darwin":
    raise ImportError("power_darwin is only available on macOS")

import objc

IOKit = ctypes.CDLL("/System/Library/Frameworks/IOKit.framework/IOKit")
CoreFoundation = ctypes.CDLL(
    "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation",
)

kCFAllocatorDefault = None
kCFStringEncodingUTF8 = 0x08000100

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


@dataclass(frozen=True)
class PowerTelemetry:
    """Point-in-time system and battery power readings."""

    system_power_w: Optional[float]
    battery_power_w: Optional[float]
    external_connected: Optional[bool]


def milliwatts_to_watts(milliwatts: int) -> float:
    """Convert milliwatts to watts.

    Args:
        milliwatts (int): Power value in milliwatts.

    Returns:
        float: Power value in watts.
    """
    return milliwatts / 1000.0


def battery_discharge_w(
    battery_power_w: Optional[float],
    system_power_w: Optional[float],
    external_connected: Optional[bool],
) -> Optional[float]:
    """Resolve the battery discharge watts to display.

    Args:
        battery_power_w (float | None): Battery discharge power in watts.
        system_power_w (float | None): Total system power in watts.
        external_connected (bool | None): Whether AC power is connected.

    Returns:
        float | None: Battery discharge watts, or None without battery telemetry.
    """
    if external_connected is None:
        return None
    if battery_power_w is not None and battery_power_w > 0:
        return battery_power_w
    if external_connected is False:
        return system_power_w
    return 0.0


def format_battery_power_part(
    battery_power_w: Optional[float],
    external_connected: Optional[bool],
    system_power_w: Optional[float] = None,
) -> Optional[str]:
    """Format battery discharge power for the tray label.

    Args:
        battery_power_w (float | None): Battery discharge power in watts.
        external_connected (bool | None): Whether AC power is connected.
        system_power_w (float | None): Total system power in watts.

    Returns:
        str | None: Compact label like ``8W``, or None when unavailable.
    """
    discharge_w = battery_discharge_w(
        battery_power_w,
        system_power_w,
        external_connected,
    )
    if discharge_w is None:
        return None
    return f"{discharge_w:.0f}W"


def read_system_power_w() -> Optional[float]:
    """Read current total system power draw in watts.

    Uses ``PowerTelemetryData.SystemPowerIn`` from AppleSmartBattery, which is
    available on Apple Silicon MacBooks. Returns None on desktops or when the
    telemetry key is missing.

    Returns:
        float | None: Total system power in watts.
    """
    return read_power_telemetry().system_power_w


def read_power_telemetry() -> PowerTelemetry:
    """Read system and battery power telemetry from AppleSmartBattery.

    Returns:
        PowerTelemetry: Latest power readings, with None fields when unavailable.
    """
    service = _open_battery_service()
    if not service:
        return PowerTelemetry(None, None, None)

    external_connected = _read_bool_property(service, "ExternalConnected")
    telemetry = _read_registry_object(service, "PowerTelemetryData")
    if not telemetry:
        return PowerTelemetry(None, None, external_connected)

    system_power_w = _optional_milliwatts(telemetry.get("SystemPowerIn"))
    battery_power_w = _optional_milliwatts(telemetry.get("BatteryPower"))
    return PowerTelemetry(system_power_w, battery_power_w, external_connected)


def _open_battery_service() -> int:
    """Return the IORegistry handle for AppleSmartBattery."""
    iterator = ctypes.c_uint32(0)
    result = IOServiceGetMatchingServices(
        0,
        IOServiceMatching(b"AppleSmartBattery"),
        ctypes.byref(iterator),
    )
    if result != 0:
        return 0
    return IOIteratorNext(iterator.value)


def _cf_string(name: str) -> Optional[int]:
    """Create a CFString for an IORegistry property name."""
    value = CFStringCreateWithCString(
        kCFAllocatorDefault,
        name.encode(),
        kCFStringEncodingUTF8,
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


def _read_bool_property(service: int, property_name: str) -> Optional[bool]:
    """Read one IORegistry boolean property."""
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
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return bool(value)
        return None
    finally:
        CFRelease(property_ref)


def _optional_milliwatts(value: object) -> Optional[float]:
    """Convert a telemetry milliwatt value to watts."""
    if value is None:
        return None
    try:
        milliwatts = int(value)
    except (TypeError, ValueError):
        return None
    if milliwatts < 0:
        milliwatts = abs(milliwatts)
    return milliwatts_to_watts(milliwatts)
