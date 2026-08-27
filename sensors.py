"""macOS sensor readers for temperature and fan speed."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from typing import Optional

from .tray_common import (
    default_label_components,
    is_gpu_metric_enabled,
    is_label_component_enabled,
)


@dataclass(frozen=True)
class GpuReading:
    """One GPU name, utilization, and temperature sample."""

    name: str
    util_pct: Optional[float] = None
    celsius: Optional[float] = None


@dataclass(frozen=True)
class GpuCoreCount:
    """Static GPU name and core count for the tooltip header."""

    name: str
    cores: int


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
    gpus: list[GpuReading] = field(default_factory=list)
    machine_model: Optional[str] = None
    chip_name: Optional[str] = None
    cpu_cores: Optional[int] = None
    gpu_core_counts: list[GpuCoreCount] = field(default_factory=list)
    disk_name: Optional[str] = None
    disk_medium: Optional[str] = None
    disk_used_gb: Optional[float] = None
    disk_total_gb: Optional[float] = None


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
        str: Text like ``C12%41° G36%40° M12G32% D126G7% S14W B8W98% F1351+ F1455+``.
            Dual-GPU machines repeat ``G`` for each GPU.
    """
    enabled = components if components is not None else default_label_components()
    parts: list[str] = []
    cpu_part = format_metric_pair_tray_part(
        "C",
        snapshot.cpu_util_pct,
        "%",
        is_label_component_enabled(enabled, "cpu_util"),
        snapshot.cpu_celsius,
        "°",
        is_label_component_enabled(enabled, "cpu_temp"),
    )
    if cpu_part is not None:
        parts.append(cpu_part)
    gpu_count = len(snapshot.gpus)
    if gpu_count > 1:
        for index, gpu in enumerate(snapshot.gpus):
            gpu_part = format_metric_pair_tray_part(
                "G",
                coalesce_gpu_util_pct(gpu.util_pct),
                "%",
                is_gpu_metric_enabled(enabled, index, "util", gpu_count),
                gpu.celsius,
                "°",
                is_gpu_metric_enabled(enabled, index, "temp", gpu_count),
            )
            if gpu_part is not None:
                parts.append(gpu_part)
    else:
        gpu_part = format_metric_pair_tray_part(
            "G",
            snapshot.gpu_util_pct,
            "%",
            is_label_component_enabled(enabled, "gpu_util"),
            snapshot.gpu_celsius,
            "°",
            is_label_component_enabled(enabled, "gpu_temp"),
        )
        if gpu_part is not None:
            parts.append(gpu_part)
    memory_part = format_memory_tray_part(
        snapshot.memory_used_gb,
        snapshot.memory_total_gb,
        show_gb=is_label_component_enabled(enabled, "memory"),
        show_pct=is_label_component_enabled(enabled, "memory_pct"),
    )
    if memory_part is not None:
        parts.append(memory_part)
    disk_part = format_disk_tray_part(
        snapshot.disk_used_gb,
        snapshot.disk_total_gb,
        show_gb=is_label_component_enabled(enabled, "disk"),
        show_pct=is_label_component_enabled(enabled, "disk_pct"),
    )
    if disk_part is not None:
        parts.append(disk_part)
    if is_label_component_enabled(enabled, "system_power"):
        if snapshot.system_power_w is not None:
            parts.append(f"S{snapshot.system_power_w:.0f}W")
    battery_part = format_battery_tray_part(
        snapshot,
        show_power=is_label_component_enabled(enabled, "battery_power"),
        show_pct=is_label_component_enabled(enabled, "battery_pct"),
    )
    if battery_part is not None:
        parts.append(battery_part)
    if is_label_component_enabled(enabled, "fans") and snapshot.fan_rpms:
        parts.extend(f"F{rpm}+" for rpm in snapshot.fan_rpms)
    if not parts:
        return "--"
    return " ".join(parts)


def format_metric_pair_tray_part(
    prefix: str,
    first_value: Optional[float],
    first_suffix: str,
    show_first: bool,
    second_value: Optional[float],
    second_suffix: str,
    show_second: bool,
) -> Optional[str]:
    """Build a merged tray segment for two related metrics.

    Args:
        prefix (str): Leading letter for the segment (for example ``C``).
        first_value (float | None): First metric value.
        first_suffix (str): Suffix for the first metric (for example ``%``).
        show_first (bool): Whether the first metric is enabled.
        second_value (float | None): Second metric value.
        second_suffix (str): Suffix for the second metric (for example ``°``).
        show_second (bool): Whether the second metric is enabled.

    Returns:
        str | None: Text like ``C12%41°``, or None when both metrics are off.
    """
    if not show_first and not show_second:
        return None
    body = ""
    if show_first:
        body += (
            f"{first_value:.0f}{first_suffix}"
            if first_value is not None
            else "--"
        )
    if show_second:
        body += (
            f"{second_value:.0f}{second_suffix}"
            if second_value is not None
            else "--"
        )
    return f"{prefix}{body}"


def gpu_tray_prefix(index: int) -> str:
    """Return the tray prefix for one GPU index.

    Args:
        index (int): Zero-based GPU index.

    Returns:
        str: Text like ``GPU0``.
    """
    return f"GPU{index}"


def coalesce_gpu_util_pct(util_pct: Optional[float]) -> float:
    """Return GPU utilization, using 0 when the driver omits a reading.

    Intel iGPUs publish ``Device Utilization %``. AMD dGPUs on Intel Macs
    often omit that key while idle, which would otherwise show as ``--``.

    Args:
        util_pct (float | None): Reported utilization, or None when missing.

    Returns:
        float: Utilization from 0 to 100.
    """
    if util_pct is None:
        return 0.0
    return float(util_pct)


def merge_gpu_readings(
    devices: list[GpuReading],
    temperatures: list[Optional[float]],
) -> list[GpuReading]:
    """Pair detected GPU devices with SMC temperatures by index.

    Extra temperature slots without a matching device are ignored so a
    single-GPU machine is not shown as GPU0/GPU1.

    Args:
        devices (list[GpuReading]): Named GPUs with utilization.
        temperatures (list[float | None]): Celsius readings aligned to GPU
            index (``TG0*``, ``TG1*``, ...).

    Returns:
        list[GpuReading]: Combined samples for available GPUs only.
    """
    readings: list[GpuReading] = []
    for index, device in enumerate(devices):
        temp = temperatures[index] if index < len(temperatures) else None
        readings.append(
            GpuReading(
                name=device.name,
                util_pct=coalesce_gpu_util_pct(device.util_pct),
                celsius=temp,
            )
        )
    return readings


def format_battery_tray_part(
    snapshot: SensorSnapshot,
    *,
    show_power: bool,
    show_pct: bool,
) -> Optional[str]:
    """Build the merged battery segment for the tray label.

    Args:
        snapshot (SensorSnapshot): Latest sensor readings.
        show_power (bool): Whether battery watts are enabled.
        show_pct (bool): Whether battery percent is enabled.

    Returns:
        str | None: Text like ``B8W98%``, or None when nothing is shown.
    """
    if not show_power and not show_pct:
        return None
    body = ""
    if show_pct:
        pct_part = _format_battery_pct_part(snapshot)
        if pct_part is not None:
            body += pct_part
    if show_power:
        power_part = _format_battery_power_part(snapshot)
        if power_part is not None:
            body += power_part
    return f"B{body}"


def _format_battery_power_part(snapshot: SensorSnapshot) -> Optional[str]:
    """Build the battery power body for the tray label."""
    from .power_darwin import format_battery_power_part

    return format_battery_power_part(
        snapshot.battery_power_w,
        snapshot.external_connected,
        snapshot.system_power_w,
    )


def _format_battery_pct_part(snapshot: SensorSnapshot) -> Optional[str]:
    """Build the battery percentage body for the tray label."""
    from .power_darwin import format_battery_pct_part

    return format_battery_pct_part(snapshot.battery_pct)


def format_tooltip(snapshot: SensorSnapshot) -> str:
    """Build a tray tooltip string from a sensor snapshot.

    Args:
        snapshot (SensorSnapshot): Latest sensor readings.

    Returns:
        str: Multi-line tooltip text, starting with the laptop model when
            known.
    """
    lines = [snapshot.machine_model] if snapshot.machine_model else ["System monitor"]
    chip_line = format_chip_tooltip(snapshot.chip_name)
    if chip_line is not None:
        lines.append(chip_line)
    disk_name_line = format_disk_name_tooltip(
        snapshot.disk_medium,
        snapshot.disk_name,
    )
    if disk_name_line is not None:
        lines.append(disk_name_line)
    cpu_line = format_util_cores_tooltip(
        "CPU",
        snapshot.cpu_util_pct,
        snapshot.cpu_cores,
        snapshot.cpu_celsius,
    )
    if cpu_line is not None:
        lines.append(cpu_line)
    lines.extend(
        format_gpu_util_cores_tooltips(
            snapshot.gpus,
            snapshot.gpu_core_counts,
            snapshot.gpu_util_pct,
            snapshot.gpu_celsius,
        )
    )
    memory_tooltip = format_memory_tooltip(
        snapshot.memory_used_gb,
        snapshot.memory_total_gb,
    )
    if memory_tooltip is not None:
        lines.append(memory_tooltip)
    disk_usage_line = format_disk_usage_tooltip(
        snapshot.disk_used_gb,
        snapshot.disk_total_gb,
    )
    if disk_usage_line is not None:
        lines.append(disk_usage_line)
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
        lines.append(f"Battery charge: {snapshot.battery_pct:.0f}%")
    if snapshot.fan_rpms:
        fan_text = ", ".join(f"Fan {index + 1}: {rpm} RPM" for index, rpm in enumerate(snapshot.fan_rpms))
        lines.append(fan_text)
    elif snapshot.cpu_celsius is not None or snapshot.gpu_celsius is not None:
        lines.append("Fans: none / fanless")
    if snapshot.error:
        lines.append(f"Warning: {snapshot.error}")
    return "\n".join(lines)


def format_chip_tooltip(chip_name: Optional[str]) -> Optional[str]:
    """Build a tooltip line for the SoC or CPU name.

    Args:
        chip_name (str | None): Marketing chip label.

    Returns:
        str | None: Chip line, or None when the name is missing.
    """
    if not chip_name:
        return None
    return f"Chip: {chip_name}"


def format_disk_name_tooltip(
    medium: Optional[str],
    name: Optional[str],
) -> Optional[str]:
    """Build a tooltip line for the internal drive model.

    Args:
        medium (str | None): ``SSD`` or ``HDD``.
        name (str | None): Drive model name.

    Returns:
        str | None: Drive identity line, or None when unknown.
    """
    if medium and name:
        return f"{medium}: {name}"
    if name:
        return f"Disk: {name}"
    if medium:
        return f"Disk: {medium}"
    return None


def format_disk_usage_tooltip(
    disk_used_gb: Optional[float],
    disk_total_gb: Optional[float],
) -> Optional[str]:
    """Build a tooltip line for used disk space.

    Args:
        disk_used_gb (float | None): Used disk space in GiB.
        disk_total_gb (float | None): Total disk space in GiB.

    Returns:
        str | None: Text like ``Disk: 127.4 / 1858.0 GB (7%)``.
    """
    if disk_used_gb is None or disk_total_gb is None or disk_total_gb <= 0:
        return None
    disk_used_pct = disk_used_gb / disk_total_gb * 100.0
    return (
        f"Disk: {disk_used_gb:.1f} / {disk_total_gb:.1f} GB "
        f"({disk_used_pct:.0f}%)"
    )


def format_util_cores_tooltip(
    prefix: str,
    util_pct: Optional[float],
    cores: Optional[int],
    celsius: Optional[float] = None,
) -> Optional[str]:
    """Build a tooltip line that merges utilization, temperature, and cores.

    Args:
        prefix (str): Label prefix such as ``CPU`` or ``GPU``.
        util_pct (float | None): Utilization percentage.
        cores (int | None): Core count.
        celsius (float | None): Temperature in Celsius.

    Returns:
        str | None: Combined line, or None when all values are missing.
    """
    parts: list[str] = []
    if util_pct is not None:
        parts.append(f"{util_pct:.0f}%")
    if celsius is not None:
        parts.append(f"{celsius:.1f}°C")
    if cores is not None:
        parts.append(f"{cores} cores")
    if not parts:
        return None
    return f"{prefix}: {' '.join(parts)}"


def format_gpu_util_cores_tooltips(
    gpus: list[GpuReading],
    gpu_core_counts: list[GpuCoreCount],
    gpu_util_pct: Optional[float],
    gpu_celsius: Optional[float] = None,
) -> list[str]:
    """Build tooltip lines that merge GPU utilization, temperature, and cores.

    Args:
        gpus (list[GpuReading]): Live GPU samples.
        gpu_core_counts (list[GpuCoreCount]): Static GPU core counts.
        gpu_util_pct (float | None): Combined GPU utilization for a single GPU.
        gpu_celsius (float | None): Combined GPU temperature for a single GPU.

    Returns:
        list[str]: One merged line, or labeled lines on dual-GPU machines.
    """
    if len(gpus) > 1 or len(gpu_core_counts) > 1:
        count = max(len(gpus), len(gpu_core_counts))
        lines: list[str] = []
        for index in range(count):
            gpu = gpus[index] if index < len(gpus) else None
            cores_info = (
                gpu_core_counts[index] if index < len(gpu_core_counts) else None
            )
            name = None
            if gpu is not None:
                name = gpu.name
            elif cores_info is not None:
                name = cores_info.name
            util_pct = coalesce_gpu_util_pct(gpu.util_pct) if gpu is not None else None
            celsius = gpu.celsius if gpu is not None else None
            cores = cores_info.cores if cores_info is not None else None
            line = format_util_cores_tooltip(
                gpu_tooltip_label(index, name),
                util_pct,
                cores,
                celsius,
            )
            if line is not None:
                lines.append(line)
        return lines
    cores = gpu_core_counts[0].cores if gpu_core_counts else None
    line = format_util_cores_tooltip("GPU", gpu_util_pct, cores, gpu_celsius)
    return [line] if line is not None else []


def gpu_tooltip_label(index: int, name: Optional[str]) -> str:
    """Build a tooltip GPU label such as ``GPU0 Intel UHD Graphics 630``.

    Args:
        index (int): Zero-based GPU index.
        name (str | None): Optional model name.

    Returns:
        str: Tooltip label prefix before the metric value.
    """
    prefix = gpu_tray_prefix(index)
    if name:
        return f"{prefix} {name}"
    return prefix


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
    machine_model: Optional[str] = None
    chip_name: Optional[str] = None
    cpu_cores: Optional[int] = None
    gpu_core_counts: list[GpuCoreCount] = []
    disk_name: Optional[str] = None
    disk_medium: Optional[str] = None
    disk_used_gb: Optional[float] = None
    disk_total_gb: Optional[float] = None
    errors: list[str] = []

    try:
        from .hardware_darwin import read_hardware_info

        hardware = read_hardware_info()
        machine_model = hardware.machine_model
        chip_name = hardware.chip_name
        cpu_cores = hardware.cpu_cores
        gpu_core_counts = [
            GpuCoreCount(name=gpu.name, cores=gpu.core_count)
            for gpu in hardware.gpus
        ]
        if hardware.disk is not None:
            disk_name = hardware.disk.name
            disk_medium = hardware.disk.medium
    except Exception as exc:
        errors.append(f"hardware: {exc}")

    try:
        usage = shutil.disk_usage("/")
        disk_used_gb, disk_total_gb = memory_bytes_to_gb_pair(
            float(usage.used),
            float(usage.total),
        )
    except OSError as exc:
        errors.append(f"disk: {exc}")

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

    gpu_devices: list[GpuReading] = []
    try:
        from .gpu_darwin import read_gpu_devices

        gpu_devices = [
            GpuReading(name=device.name, util_pct=device.util_pct)
            for device in read_gpu_devices()
        ]
    except Exception as exc:
        errors.append(f"gpu_util: {exc}")

    gpu_temps: list[Optional[float]] = []
    if gpu_devices:
        try:
            from .smc_darwin import read_gpu_temperatures

            gpu_temps = read_gpu_temperatures(max_gpus=len(gpu_devices))
        except Exception as exc:
            errors.append(f"smc_gpu_temps: {exc}")

    gpus = merge_gpu_readings(gpu_devices, gpu_temps)
    if gpu_util_pct is None:
        util_values = [gpu.util_pct for gpu in gpus if gpu.util_pct is not None]
        if util_values:
            gpu_util_pct = max(util_values)
    if gpu_celsius is None:
        for gpu in gpus:
            if gpu.celsius is not None:
                gpu_celsius = gpu.celsius
                break

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
        gpus=gpus,
        machine_model=machine_model,
        chip_name=chip_name,
        cpu_cores=cpu_cores,
        gpu_core_counts=gpu_core_counts,
        disk_name=disk_name,
        disk_medium=disk_medium,
        disk_used_gb=disk_used_gb,
        disk_total_gb=disk_total_gb,
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
    *,
    show_gb: bool = True,
    show_pct: bool = True,
) -> Optional[str]:
    """Build the used-memory segment for the tray label.

    Args:
        memory_used_gb (float | None): Used memory in GiB.
        memory_total_gb (float | None): Total memory in GiB.
        show_gb (bool): Whether used GiB is enabled.
        show_pct (bool): Whether used percent is enabled.

    Returns:
        str | None: Text like ``M20G40%``, or None when nothing is shown.
    """
    if not show_gb and not show_pct:
        return None
    if memory_used_gb is None or memory_total_gb is None or memory_total_gb <= 0:
        return None
    body = ""
    if show_pct:
        memory_used_pct = memory_used_gb / memory_total_gb * 100.0
        body += f"{memory_used_pct:.0f}%"
    if show_gb:
        body += f"{memory_used_gb:.0f}G"
    return f"M{body}"


def format_disk_tray_part(
    disk_used_gb: Optional[float],
    disk_total_gb: Optional[float],
    *,
    show_gb: bool = True,
    show_pct: bool = True,
) -> Optional[str]:
    """Build the used-disk segment for the tray label.

    Args:
        disk_used_gb (float | None): Used disk space in GiB.
        disk_total_gb (float | None): Total disk space in GiB.
        show_gb (bool): Whether used GiB is enabled.
        show_pct (bool): Whether used percent is enabled.

    Returns:
        str | None: Text like ``D126G7%``, or None when nothing is shown.
    """
    if not show_gb and not show_pct:
        return None
    if disk_used_gb is None or disk_total_gb is None or disk_total_gb <= 0:
        return None
    body = ""
    if show_pct:
        disk_used_pct = disk_used_gb / disk_total_gb * 100.0
        body += f"{disk_used_pct:.0f}%"
    if show_gb:
        body += f"{disk_used_gb:.0f}G"
    return f"D{body}"


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
