"""macOS sensor readers for temperature and fan speed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .tray_common import default_label_components, is_label_component_enabled


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
    battery_pct: Optional[float] = None
    error: Optional[str] = None


def format_tray_label(
    snapshot: SensorSnapshot,
    components: Optional[dict[str, bool]] = None,
) -> str:
    """Build a compact single-line label for the tray icon.

    Args:
        snapshot (SensorSnapshot): Latest sensor readings.
        components (dict[str, bool] | None): Enabled map for label segments.
            When None, all components are shown.

    Returns:
        str: Text like ``c12% c41° g36% g40° s14W b8W b98% f1351+ f1455+``.
    """
    enabled = components if components is not None else default_label_components()
    parts: list[str] = []
    if is_label_component_enabled(enabled, "cpu_util"):
        parts.append(
            f"c{snapshot.cpu_util_pct:.0f}%"
            if snapshot.cpu_util_pct is not None
            else "c--"
        )
    if is_label_component_enabled(enabled, "cpu_temp"):
        parts.append(
            f"c{snapshot.cpu_celsius:.0f}°"
            if snapshot.cpu_celsius is not None
            else "c--"
        )
    if is_label_component_enabled(enabled, "gpu_util"):
        parts.append(
            f"g{snapshot.gpu_util_pct:.0f}%"
            if snapshot.gpu_util_pct is not None
            else "g--"
        )
    if is_label_component_enabled(enabled, "gpu_temp"):
        parts.append(
            f"g{snapshot.gpu_celsius:.0f}°"
            if snapshot.gpu_celsius is not None
            else "g--"
        )
    if is_label_component_enabled(enabled, "system_power"):
        if snapshot.system_power_w is not None:
            parts.append(f"s{snapshot.system_power_w:.0f}W")
    if is_label_component_enabled(enabled, "battery_power"):
        battery_part = _format_battery_power_part(snapshot)
        if battery_part is not None:
            parts.append(battery_part)
    if is_label_component_enabled(enabled, "battery_pct"):
        battery_pct_part = _format_battery_pct_part(snapshot)
        if battery_pct_part is not None:
            parts.append(battery_pct_part)
    if is_label_component_enabled(enabled, "fans") and snapshot.fan_rpms:
        parts.extend(f"f{rpm}+" for rpm in snapshot.fan_rpms)
    if not parts:
        return "--"
    return " ".join(parts)


def _format_battery_power_part(snapshot: SensorSnapshot) -> Optional[str]:
    """Build the battery power segment for the tray label."""
    from .power_darwin import format_battery_power_part

    return format_battery_power_part(
        snapshot.battery_power_w,
        snapshot.external_connected,
        snapshot.system_power_w,
    )


def _format_battery_pct_part(snapshot: SensorSnapshot) -> Optional[str]:
    """Build the battery percentage segment for the tray label."""
    from .power_darwin import format_battery_pct_part

    return format_battery_pct_part(snapshot.battery_pct)


def format_tooltip(snapshot: SensorSnapshot) -> str:
    """Build a tray tooltip string from a sensor snapshot.

    Args:
        snapshot (SensorSnapshot): Latest sensor readings.

    Returns:
        str: Multi-line tooltip text.
    """
    lines = ["System monitor"]
    if snapshot.cpu_celsius is not None:
        lines.append(f"CPU: {snapshot.cpu_celsius:.1f}°C")
    if snapshot.cpu_util_pct is not None:
        lines.append(f"CPU: {snapshot.cpu_util_pct:.0f}%")
    if snapshot.gpu_celsius is not None:
        lines.append(f"GPU: {snapshot.gpu_celsius:.1f}°C")
    if snapshot.gpu_util_pct is not None:
        lines.append(f"GPU: {snapshot.gpu_util_pct:.0f}%")
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
    if snapshot.battery_pct is not None:
        lines.append(f"Battery: {snapshot.battery_pct:.0f}%")
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
    battery_pct: Optional[float] = None
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
        battery_pct = power.battery_pct
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
        battery_pct=battery_pct,
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
