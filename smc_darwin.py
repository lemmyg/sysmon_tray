"""Read fan speeds from the Apple System Management Controller."""

from __future__ import annotations

import ctypes
import struct
import sys
from typing import Optional

if sys.platform != "darwin":
    raise ImportError("smc_darwin is only available on macOS")

IOKit = ctypes.CDLL("/System/Library/Frameworks/IOKit.framework/IOKit")

SMC_CMD_READ_KEYINFO = 9
SMC_CMD_READ_BYTES = 5
KERNEL_INDEX_SMC = 2
TASK_SELF = 0x203
SMC_TYPE_FLOAT = int.from_bytes(b"flt ", "big")


class _SMCVers(ctypes.Structure):
    _fields_ = [
        ("major", ctypes.c_char),
        ("minor", ctypes.c_char),
        ("build", ctypes.c_char),
        ("reserved", ctypes.c_char),
        ("release", ctypes.c_uint16),
    ]


class _SMCPLimit(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_uint16),
        ("length", ctypes.c_uint16),
        ("cpu_p_limit", ctypes.c_uint32),
        ("gpu_p_limit", ctypes.c_uint32),
        ("mem_p_limit", ctypes.c_uint32),
    ]


class _SMCKeyInfo(ctypes.Structure):
    _fields_ = [
        ("data_size", ctypes.c_uint32),
        ("data_type", ctypes.c_uint32),
        ("data_attributes", ctypes.c_char),
    ]


class _SMCKeyData(ctypes.Structure):
    _fields_ = [
        ("key", ctypes.c_uint32),
        ("vers", _SMCVers),
        ("p_limit_data", _SMCPLimit),
        ("key_info", _SMCKeyInfo),
        ("result", ctypes.c_uint8),
        ("status", ctypes.c_uint8),
        ("data8", ctypes.c_uint8),
        ("data32", ctypes.c_uint32),
        ("bytes", ctypes.c_char * 32),
    ]


_BYTES_OFFSET = _SMCKeyData.bytes.offset

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
IOServiceOpen = IOKit.IOServiceOpen
IOServiceOpen.restype = ctypes.c_int
IOServiceOpen.argtypes = [
    ctypes.c_uint32,
    ctypes.c_uint32,
    ctypes.c_uint32,
    ctypes.POINTER(ctypes.c_uint32),
]
IOConnectCallStructMethod = IOKit.IOConnectCallStructMethod
IOConnectCallStructMethod.restype = ctypes.c_int
IOConnectCallStructMethod.argtypes = [
    ctypes.c_uint32,
    ctypes.c_uint32,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_size_t),
]
IOServiceClose = IOKit.IOServiceClose


def smc_key_to_uint(key: str) -> int:
    """Encode a four-character SMC key as a big-endian uint32.

    Args:
        key (str): Four-character SMC key, for example ``F0Ac``.

    Returns:
        int: Encoded key value.
    """
    if len(key) != 4:
        raise ValueError(f"SMC key must be exactly 4 characters, got {key!r}")
    return (
        (ord(key[0]) << 24)
        | (ord(key[1]) << 16)
        | (ord(key[2]) << 8)
        | ord(key[3])
    )


def decode_smc_value(raw: bytes, data_type: int, data_size: int) -> Optional[float]:
    """Decode raw SMC bytes into a numeric sensor value.

    Args:
        raw (bytes): Raw payload bytes from the SMC key.
        data_type (int): SMC data-type tag.
        data_size (int): Number of payload bytes.

    Returns:
        float | None: Decoded value, or None when the format is unsupported.
    """
    if data_size == 0 or len(raw) < data_size:
        return None
    payload = raw[:data_size]
    if data_type == SMC_TYPE_FLOAT and data_size == 4:
        return float(struct.unpack("<f", payload)[0])
    if data_size == 2:
        return struct.unpack(">H", payload)[0] / 256.0
    if data_size == 1:
        return float(payload[0])
    return None


# Intel Macs use TC*/TG*; Apple Silicon uses Tp*/Tg* (scanned by darwin-perf).
CPU_TEMP_KEYS = (
    "TC0P",
    "TC0E",
    "TC0F",
    "Tp0P",
    "Tp01",
    "Tp05",
)
GPU_TEMP_KEYS = (
    "TG0P",
    "TG0D",
    "Tg0P",
    "Tg0D",
)
CPU_CORE_TEMP_KEYS = tuple(f"TC{index}C" for index in range(1, 9))


def select_temperature(
    readings: dict[str, float],
    preferred_keys: tuple[str, ...],
) -> Optional[float]:
    """Pick the first available temperature from preferred SMC keys.

    Args:
        readings (dict[str, float]): Map of SMC key to Celsius.
        preferred_keys (tuple[str, ...]): Keys to try in priority order.

    Returns:
        float | None: First present reading, or None when none match.
    """
    for key in preferred_keys:
        value = readings.get(key)
        if value is not None:
            return float(value)
    return None


def average_temperatures(values: list[float]) -> Optional[float]:
    """Average a list of Celsius readings.

    Args:
        values (list[float]): Temperature samples in Celsius.

    Returns:
        float | None: Mean temperature, or None when the list is empty.
    """
    if not values:
        return None
    return sum(values) / float(len(values))


def read_die_temperatures() -> tuple[Optional[float], Optional[float]]:
    """Read CPU and GPU die temperatures from AppleSMC.

    Intel Macs expose package/core keys such as ``TC0P`` / ``TG0P``. Apple
    Silicon typically uses ``Tp*`` / ``Tg*``. When package CPU keys are
    missing, core keys ``TC1C``..``TC8C`` are averaged as a fallback.

    Returns:
        tuple[float | None, float | None]: CPU and GPU Celsius readings.
    """
    connection = _open_smc_connection()
    if connection is None:
        return None, None

    try:
        cpu_keys = CPU_TEMP_KEYS + CPU_CORE_TEMP_KEYS
        gpu_keys = GPU_TEMP_KEYS
        readings: dict[str, float] = {}
        for key in (*cpu_keys, *gpu_keys):
            value = _read_smc_key(connection, key)
            if value is not None and 0.0 < value < 150.0:
                readings[key] = float(value)

        cpu_celsius = select_temperature(readings, CPU_TEMP_KEYS)
        if cpu_celsius is None:
            core_values = [
                readings[key] for key in CPU_CORE_TEMP_KEYS if key in readings
            ]
            cpu_celsius = average_temperatures(core_values)
        gpu_celsius = select_temperature(readings, GPU_TEMP_KEYS)
        return cpu_celsius, gpu_celsius
    finally:
        IOServiceClose(connection)


def read_fan_speeds(max_fans: int = 4) -> list[int]:
    """Read current fan speeds in RPM from AppleSMC.

    The fan count is taken from the ``FNum`` key so that present-but-stopped
    fans (0 RPM, common on Apple Silicon when cool) are still reported. When
    ``FNum`` is unavailable, up to ``max_fans`` indices are probed instead.

    Args:
        max_fans (int): Maximum number of fan indices to probe when the fan
            count key ``FNum`` cannot be read.

    Returns:
        list[int]: Fan speeds in RPM for each present fan, including 0 RPM.
    """
    connection = _open_smc_connection()
    if connection is None:
        return []

    fans: list[int] = []
    try:
        fan_count = _read_smc_key(connection, "FNum")
        count = int(fan_count) if fan_count is not None else max_fans
        for index in range(count):
            key = f"F{index}Ac"
            rpm = _read_smc_key(connection, key)
            if rpm is None:
                continue
            fans.append(int(round(max(0.0, rpm))))
    finally:
        IOServiceClose(connection)

    return fans


def _open_smc_connection() -> Optional[int]:
    """Open an IOKit connection to AppleSMC.

    Returns:
        int | None: Connection handle, or None when AppleSMC is unavailable.
    """
    iterator = ctypes.c_uint32(0)
    result = IOServiceGetMatchingServices(
        0,
        IOServiceMatching(b"AppleSMC"),
        ctypes.byref(iterator),
    )
    if result != 0:
        return None

    service = IOIteratorNext(iterator.value)
    if not service:
        return None

    connection = ctypes.c_uint32(0)
    result = IOServiceOpen(service, TASK_SELF, 0, ctypes.byref(connection))
    if result != 0:
        return None
    return int(connection.value)


def _read_smc_key(connection: int, key: str) -> Optional[float]:
    """Read one SMC key as a float-like value."""
    input_struct = _SMCKeyData()
    output_struct = _SMCKeyData()
    input_struct.key = smc_key_to_uint(key)
    input_struct.data8 = SMC_CMD_READ_KEYINFO
    output_size = ctypes.c_size_t(ctypes.sizeof(output_struct))
    result = IOConnectCallStructMethod(
        connection,
        KERNEL_INDEX_SMC,
        ctypes.byref(input_struct),
        ctypes.sizeof(input_struct),
        ctypes.byref(output_struct),
        ctypes.byref(output_size),
    )
    if result != 0 or output_struct.key_info.data_size == 0:
        return None

    read_input = _SMCKeyData()
    read_output = _SMCKeyData()
    read_input.key = input_struct.key
    read_input.key_info = output_struct.key_info
    read_input.data8 = SMC_CMD_READ_BYTES
    output_size = ctypes.c_size_t(ctypes.sizeof(read_output))
    result = IOConnectCallStructMethod(
        connection,
        KERNEL_INDEX_SMC,
        ctypes.byref(read_input),
        ctypes.sizeof(read_input),
        ctypes.byref(read_output),
        ctypes.byref(output_size),
    )
    if result != 0:
        return None

    raw = bytes(read_output)[_BYTES_OFFSET : _BYTES_OFFSET + output_struct.key_info.data_size]
    return decode_smc_value(
        raw,
        output_struct.key_info.data_type,
        output_struct.key_info.data_size,
    )
