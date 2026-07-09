"""macOS sensor readers for temperature and fan speed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SensorSnapshot:
    """Point-in-time temperature, utilization, fan, and power readings."""

    cpu_celsius: Optional[float]
    gpu_celsius: Optional[float]
    cpu_util_pct: Optional[float]
    gpu_util_pct: Optional[float]
    fan_rpms: list[int]
    system_power_w: Optional[float] = None
    battery_power_w: Optional[float] = None
    external_connected: Optional[bool] = None
    error: Optional[str] = None


def format_tray_label(snapshot: SensorSnapshot) -> str:
    """Build a compact single-line label for the tray icon.

    Args:
        snapshot (SensorSnapshot): Latest sensor readings.

    Returns:
        str: Text like ``12% | 41C | 36% | 40C | 14W | 8W | 1351+ | 1455+``.
    """
    cpu_util = (
        f"{snapshot.cpu_util_pct:.0f}%"
        if snapshot.cpu_util_pct is not None
        else "--"
    )
    cpu_c = (
        f"{snapshot.cpu_celsius:.0f}C"
        if snapshot.cpu_celsius is not None
        else "--"
    )
    gpu_util = (
        f"{snapshot.gpu_util_pct:.0f}%"
        if snapshot.gpu_util_pct is not None
        else "--"
    )
    gpu_c = (
        f"{snapshot.gpu_celsius:.0f}C"
        if snapshot.gpu_celsius is not None
        else "--"
    )
    parts = [cpu_util, cpu_c, gpu_util, gpu_c]
    if snapshot.system_power_w is not None:
        parts.append(f"{snapshot.system_power_w:.0f}W")
    battery_part = _format_battery_power_part(snapshot)
    if battery_part is not None:
        parts.append(battery_part)
    if snapshot.fan_rpms:
        parts.extend(f"{rpm}+" for rpm in snapshot.fan_rpms)
    return " | ".join(parts)


def _format_battery_power_part(snapshot: SensorSnapshot) -> Optional[str]:
    """Build the battery power segment for the tray label."""
    from .power_darwin import format_battery_power_part

    return format_battery_power_part(
        snapshot.battery_power_w,
        snapshot.external_connected,
        snapshot.system_power_w,
    )


def format_tooltip(snapshot: SensorSnapshot) -> str:
    """Build a tray tooltip string from a sensor snapshot.

    Args:
        snapshot (SensorSnapshot): Latest sensor readings.

    Returns:
        str: Multi-line tooltip text.
    """
    lines = ["System monitor"]
    if snapshot.cpu_celsius is not None:
        lines.append(f"CPU: {snapshot.cpu_celsius:.1f} C")
    if snapshot.cpu_util_pct is not None:
        lines.append(f"CPU util: {snapshot.cpu_util_pct:.0f}%")
    if snapshot.gpu_celsius is not None:
        lines.append(f"GPU: {snapshot.gpu_celsius:.1f} C")
    if snapshot.gpu_util_pct is not None:
        lines.append(f"GPU util: {snapshot.gpu_util_pct:.0f}%")
    if snapshot.system_power_w is not None:
        lines.append(f"System power: {snapshot.system_power_w:.1f} W")
    battery_part = _format_battery_power_part(snapshot)
    if battery_part is not None:
        from .power_darwin import battery_discharge_w

        discharge_w = battery_discharge_w(
            snapshot.battery_power_w,
            snapshot.system_power_w,
            snapshot.external_connected,
        )
        if discharge_w is not None:
            lines.append(f"Battery power: {discharge_w:.1f} W")
    if snapshot.fan_rpms:
        fan_text = ", ".join(f"Fan {index + 1}: {rpm} RPM" for index, rpm in enumerate(snapshot.fan_rpms))
        lines.append(fan_text)
    elif snapshot.cpu_celsius is not None or snapshot.gpu_celsius is not None:
        lines.append("Fans: none / fanless")
    if snapshot.error:
        lines.append(f"Warning: {snapshot.error}")
    return "\n".join(lines)


def read_sensors() -> SensorSnapshot:
    """Read current CPU/GPU temperature and fan speeds on macOS.

    Returns:
        SensorSnapshot: Latest readings from darwin-perf and Apple SMC.
    """
    cpu_celsius: Optional[float] = None
    gpu_celsius: Optional[float] = None
    cpu_util_pct: Optional[float] = None
    gpu_util_pct: Optional[float] = None
    fan_rpms: list[int] = []
    system_power_w: Optional[float] = None
    battery_power_w: Optional[float] = None
    external_connected: Optional[bool] = None
    errors: list[str] = []

    try:
        from darwin_perf import system_gpu_stats, system_stats, temperatures

        temps = temperatures()
        cpu_celsius = _optional_float(temps.get("cpu_avg"))
        gpu_celsius = _optional_float(temps.get("gpu_avg"))

        sys_stats = system_stats()
        cpu_user = _optional_float(sys_stats.get("cpu_user_pct"))
        cpu_system = _optional_float(sys_stats.get("cpu_system_pct"))
        if cpu_user is not None and cpu_system is not None:
            cpu_util_pct = cpu_user + cpu_system

        gpu_stats = system_gpu_stats()
        gpu_util_pct = _optional_float(gpu_stats.get("device_utilization"))
    except Exception as exc:
        errors.append(f"sensors: {exc}")

    try:
        from .smc_darwin import read_fan_speeds

        fan_rpms = read_fan_speeds()
    except Exception as exc:
        errors.append(f"fans: {exc}")

    try:
        from .power_darwin import read_power_telemetry

        power = read_power_telemetry()
        system_power_w = power.system_power_w
        battery_power_w = power.battery_power_w
        external_connected = power.external_connected
    except Exception as exc:
        errors.append(f"power: {exc}")

    return SensorSnapshot(
        cpu_celsius=cpu_celsius,
        gpu_celsius=gpu_celsius,
        cpu_util_pct=cpu_util_pct,
        gpu_util_pct=gpu_util_pct,
        fan_rpms=fan_rpms,
        system_power_w=system_power_w,
        battery_power_w=battery_power_w,
        external_connected=external_connected,
        error="; ".join(errors) if errors else None,
    )


def _optional_float(value: object) -> Optional[float]:
    """Convert a value to float when it is numeric."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
