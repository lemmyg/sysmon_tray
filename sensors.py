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
    memory_used_gb: Optional[float] = None
    memory_total_gb: Optional[float] = None
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
    if is_label_component_enabled(enabled, "memory"):
        memory_part = format_memory_tray_part(
            snapshot.memory_used_gb,
            snapshot.memory_total_gb,
        )
        if memory_part is not None:
            parts.append(memory_part)
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
    memory_tooltip = format_memory_tooltip(
        snapshot.memory_used_gb,
        snapshot.memory_total_gb,
    )
    if memory_tooltip is not None:
        lines.append(memory_tooltip)
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
    memory_used_gb: Optional[float] = None
    memory_total_gb: Optional[float] = None
    fan_rpms: list[int] = []
    system_power_w: Optional[float] = None
    battery_power_w: Optional[float] = None
    external_connected: Optional[bool] = None
    battery_pct: Optional[float] = None
    errors: list[str] = []

    try:
        system_gpu_stats, system_stats, temperatures = _darwin_perf_readers()

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

        memory_used_bytes = memory_used_bytes_from_stats(
            _optional_float(sys_stats.get("memory_used")),
            _optional_float(sys_stats.get("memory_available")),
            _optional_float(sys_stats.get("memory_free")),
            _optional_float(sys_stats.get("memory_inactive")),
        )
        memory_total_bytes = _optional_float(sys_stats.get("memory_total"))
        memory_used_gb, memory_total_gb = memory_bytes_to_gb_pair(
            memory_used_bytes,
            memory_total_bytes,
        )
    except Exception as exc:
        errors.append(f"sensors: {exc}")

    if cpu_celsius is None or gpu_celsius is None:
        try:
            from .smc_darwin import read_die_temperatures

            smc_cpu, smc_gpu = read_die_temperatures()
            if cpu_celsius is None:
                cpu_celsius = smc_cpu
            if gpu_celsius is None:
                gpu_celsius = smc_gpu
        except Exception as exc:
            errors.append(f"smc_temps: {exc}")

    if gpu_util_pct is None:
        try:
            from .gpu_darwin import read_device_utilization_pct

            gpu_util_pct = read_device_utilization_pct()
        except Exception as exc:
            errors.append(f"gpu_util: {exc}")

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
        memory_used_gb=memory_used_gb,
        memory_total_gb=memory_total_gb,
        fan_rpms=fan_rpms,
        system_power_w=system_power_w,
        battery_power_w=battery_power_w,
        external_connected=external_connected,
        battery_pct=battery_pct,
        error="; ".join(errors) if errors else None,
    )


def _darwin_perf_readers():
    """Return darwin-perf readers, preferring the native module on Intel.

    darwin-perf only wires its native backend on Apple Silicon. On Intel Macs
    the public API falls back to empty CPU/GPU helpers, while ``_native`` still
    provides working ``system_stats`` (CPU util and memory).

    Returns:
        tuple: ``(system_gpu_stats, system_stats, temperatures)`` callables.
    """
    import platform

    if platform.system() == "Darwin" and platform.machine() == "x86_64":
        try:
            from darwin_perf import _native

            return (
                _native.system_gpu_stats,
                _native.system_stats,
                _native.temperatures,
            )
        except ImportError:
            pass

    from darwin_perf import system_gpu_stats, system_stats, temperatures

    return system_gpu_stats, system_stats, temperatures


def memory_speculative_bytes(
    memory_available: Optional[float],
    memory_free: Optional[float],
    memory_inactive: Optional[float],
) -> Optional[float]:
    """Estimate speculative memory bytes from Mach VM statistics.

    Args:
        memory_available (float | None): Free + inactive + speculative bytes.
        memory_free (float | None): Free page bytes.
        memory_inactive (float | None): Inactive page bytes.

    Returns:
        float | None: Speculative memory in bytes when all inputs are present.
    """
    if (
        memory_available is None
        or memory_free is None
        or memory_inactive is None
    ):
        return None
    speculative = memory_available - memory_free - memory_inactive
    return max(0.0, speculative)


def memory_used_bytes_from_stats(
    memory_used: Optional[float],
    memory_available: Optional[float],
    memory_free: Optional[float],
    memory_inactive: Optional[float],
) -> Optional[float]:
    """Compute macOS-style used memory bytes from darwin-perf stats.

    Includes active, wired, compressed, and speculative memory so the tray
    value aligns with macOS system tools more closely than ``memory_used``
    alone.

    Args:
        memory_used (float | None): Active + wired + compressed bytes.
        memory_available (float | None): Free + inactive + speculative bytes.
        memory_free (float | None): Free page bytes.
        memory_inactive (float | None): Inactive page bytes.

    Returns:
        float | None: Used memory in bytes when inputs are available.
    """
    if memory_used is None:
        return None
    speculative = memory_speculative_bytes(
        memory_available,
        memory_free,
        memory_inactive,
    )
    if speculative is None:
        return None
    return memory_used + speculative


def memory_bytes_to_gb(memory_bytes: float) -> float:
    """Convert a byte count to gibibytes.

    Args:
        memory_bytes (float): Memory size in bytes.

    Returns:
        float: Equivalent size in GiB.
    """
    return float(memory_bytes) / (1024 ** 3)


def memory_bytes_to_gb_pair(
    used_bytes: Optional[float],
    total_bytes: Optional[float],
) -> tuple[Optional[float], Optional[float]]:
    """Convert used and total memory byte counts to gibibytes.

    Args:
        used_bytes (float | None): Used memory in bytes.
        total_bytes (float | None): Total memory in bytes.

    Returns:
        tuple[float | None, float | None]: Used and total GiB, or (None, None)
            when either input is missing or total is zero.
    """
    if used_bytes is None or total_bytes is None or total_bytes <= 0:
        return None, None
    return memory_bytes_to_gb(used_bytes), memory_bytes_to_gb(total_bytes)


def format_memory_tray_part(
    memory_used_gb: Optional[float],
    memory_total_gb: Optional[float],
) -> Optional[str]:
    """Build the used-memory segment for the tray label.

    Args:
        memory_used_gb (float | None): Used memory in GiB.
        memory_total_gb (float | None): Total memory in GiB.

    Returns:
        str | None: Text like ``m11.5G`` when used memory is available.
    """
    if memory_used_gb is None or memory_total_gb is None:
        return None
    return f"m{memory_used_gb:.1f}G"


def format_memory_tooltip(
    memory_used_gb: Optional[float],
    memory_total_gb: Optional[float],
) -> Optional[str]:
    """Build a tooltip line for used memory.

    Args:
        memory_used_gb (float | None): Used memory in GiB.
        memory_total_gb (float | None): Total memory in GiB.

    Returns:
        str | None: Text like ``Memory: 9.5 / 36.0 GB (26%)``.
    """
    if memory_used_gb is None or memory_total_gb is None or memory_total_gb <= 0:
        return None
    memory_used_pct = memory_used_gb / memory_total_gb * 100.0
    return (
        f"Memory: {memory_used_gb:.1f} / {memory_total_gb:.1f} GB "
        f"({memory_used_pct:.0f}%)"
    )


def _optional_float(value: object) -> Optional[float]:
    """Convert a value to float when it is numeric."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
