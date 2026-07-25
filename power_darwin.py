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
    battery_pct: Optional[float] = None


def milliwatts_to_watts(milliwatts: int) -> float:
    """Convert milliwatts to watts.

    Args:
        milliwatts (int): Power value in milliwatts.

    Returns:
        float: Power value in watts.
    """
    return milliwatts / 1000.0


def battery_power_from_voltage_amperage(
    voltage_mv: Optional[int],
    amperage_ma: Optional[int],
) -> Optional[float]:
    """Compute battery power in watts from millivolt and milliamp readings.

    Intel Macs often leave ``PowerTelemetryData.BatteryPower`` at 0 and instead
    expose pack ``Voltage`` (mV) and ``InstantAmperage`` (mA). Negative
    amperage means discharge on AppleSmartBattery.

    Args:
        voltage_mv (int | None): Pack voltage in millivolts.
        amperage_ma (int | None): Pack current in milliamps.

    Returns:
        float | None: Discharge watts when current is negative, 0.0 when
            charging or idle, or None when inputs are missing.
    """
    if voltage_mv is None or amperage_ma is None:
        return None
    watts = (float(voltage_mv) * float(amperage_ma)) / 1_000_000.0
    if watts < 0.0:
        return -watts
    return 0.0


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
        str | None: Compact label like ``b8W``, or None when unavailable.
    """
    discharge_w = battery_discharge_w(
        battery_power_w,
        system_power_w,
        external_connected,
    )
    if discharge_w is None:
        return None
    return f"b{discharge_w:.0f}W"


def battery_percent(
    current_capacity: Optional[int],
    max_capacity: Optional[int],
) -> Optional[float]:
    """Resolve battery charge percentage from AppleSmartBattery capacities.

    Args:
        current_capacity (int | None): CurrentCapacity registry value.
        max_capacity (int | None): MaxCapacity registry value.

    Returns:
        float | None: Charge percentage from 0 to 100, or None when unavailable.
    """
    if current_capacity is None:
        return None
    if max_capacity is not None and max_capacity > 0:
        if max_capacity == 100:
            return float(current_capacity)
        return 100.0 * float(current_capacity) / float(max_capacity)
    if 0 <= current_capacity <= 100:
        return float(current_capacity)
    return None


def format_battery_pct_part(battery_pct: Optional[float]) -> Optional[str]:
    """Format battery charge percentage for the tray label.

    Args:
        battery_pct (float | None): Battery charge percentage.

    Returns:
        str | None: Compact label like ``b98%``, or None when unavailable.
    """
    if battery_pct is None:
        return None
    return f"b{battery_pct:.0f}%"


def read_system_power_w() -> Optional[float]:
    """Read current total system power draw in watts.

    Prefers ``PowerTelemetryData.SystemPowerIn`` (Apple Silicon). Falls back to
    ``BatteryData.SystemPower`` on Intel, then to pack discharge while on
    battery when no separate system sensor exists.

    Returns:
        float | None: Total system power in watts.
    """
    return read_power_telemetry().system_power_w


def read_power_telemetry() -> PowerTelemetry:
    """Read system and battery power telemetry from AppleSmartBattery.

    ``system_power_w`` is main system power draw. ``battery_power_w`` is pack
    discharge. On Intel Macs while on battery those often match because the
    only available sensors measure pack output; on Apple Silicon (and on AC)
    they can diverge.

    Returns:
        PowerTelemetry: Latest power readings, with None fields when unavailable.
    """
    service = _open_battery_service()
    if not service:
        return PowerTelemetry(None, None, None, None)

    external_connected = _read_bool_property(service, "ExternalConnected")
    battery_pct = battery_percent(
        _read_int_property(service, "CurrentCapacity"),
        _read_int_property(service, "MaxCapacity"),
    )

    system_power_w: Optional[float] = None
    battery_power_w: Optional[float] = None

    telemetry = _read_registry_object(service, "PowerTelemetryData")
    if telemetry:
        system_power_w = _nonzero_milliwatts(telemetry.get("SystemPowerIn"))
        battery_power_w = _nonzero_milliwatts(telemetry.get("BatteryPower"))

    if battery_power_w is None:
        battery_power_w = battery_power_from_voltage_amperage(
            _read_int_property(service, "Voltage"),
            _read_int_property(service, "InstantAmperage"),
        )

    if system_power_w is None:
        battery_data = _read_registry_object(service, "BatteryData") or {}
        system_power_w = _optional_float(battery_data.get("SystemPower"))
        if system_power_w is not None and system_power_w <= 0.0:
            system_power_w = None
        if system_power_w is None and external_connected is True:
            adapter_power_w = _optional_float(battery_data.get("AdapterPower"))
            if adapter_power_w is not None and adapter_power_w > 0.0:
                system_power_w = adapter_power_w

    if system_power_w is None and external_connected is False:
        system_power_w = battery_power_w

    return PowerTelemetry(
        system_power_w,
        battery_power_w,
        external_connected,
        battery_pct,
    )


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


def _read_int_property(service: int, property_name: str) -> Optional[int]:
    """Read one IORegistry integer property.

    Args:
        service (int): AppleSmartBattery IORegistry handle.
        property_name (str): Registry property name.

    Returns:
        int | None: Integer value, or None when missing or non-numeric.
    """
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
            return None
        if isinstance(value, int):
            return int(value)
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


def _nonzero_milliwatts(value: object) -> Optional[float]:
    """Convert milliwatts to watts, treating zero as unavailable.

    Args:
        value (object): Raw milliwatt telemetry value.

    Returns:
        float | None: Watts when positive, otherwise None.
    """
    watts = _optional_milliwatts(value)
    if watts is None or watts <= 0.0:
        return None
    return watts


def _optional_float(value: object) -> Optional[float]:
    """Convert a value to float when it is numeric.

    Args:
        value (object): Raw registry value.

    Returns:
        float | None: Parsed float, or None when missing/non-numeric.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
