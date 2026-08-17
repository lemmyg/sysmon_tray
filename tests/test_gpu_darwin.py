"""Unit tests for Intel/macOS GPU utilization helpers."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from ..gpu_darwin import (
    GpuDevice,
    decode_registry_model,
    device_utilization_from_performance_statistics,
    gpu_display_name,
    is_gpu_accelerator,
    sort_gpu_devices,
    unique_gpu_devices,
)


def _load_cases() -> dict:
    fixture_path = Path(__file__).with_suffix(".yaml")
    with fixture_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


class TestGpuDarwin(unittest.TestCase):
    """Validate PerformanceStatistics utilization parsing."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = _load_cases()

    def test_device_utilization_from_performance_statistics(self) -> None:
        for case in self.cases[
            "device_utilization_from_performance_statistics"
        ]:
            with self.subTest(name=case["name"]):
                value = device_utilization_from_performance_statistics(
                    case["stats"],
                )
                if case["expected"] is None:
                    self.assertIsNone(value)
                else:
                    self.assertAlmostEqual(case["expected"], value, places=3)

    def test_decode_registry_model(self) -> None:
        for case in self.cases["decode_registry_model"]:
            with self.subTest(name=case["name"]):
                raw = bytes.fromhex(case["value_hex"]) if case["value_hex"] else b""
                self.assertEqual(case["expected"], decode_registry_model(raw))

    def test_gpu_display_name(self) -> None:
        for case in self.cases["gpu_display_name"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    gpu_display_name(case.get("io_class"), case.get("model")),
                )

    def test_sort_gpu_devices(self) -> None:
        for case in self.cases["sort_gpu_devices"]:
            with self.subTest(name=case["name"]):
                devices = [GpuDevice(**device) for device in case["devices"]]
                sorted_devices = sort_gpu_devices(devices)
                self.assertEqual(
                    case["expected"],
                    [
                        {"name": device.name, "util_pct": device.util_pct}
                        for device in sorted_devices
                    ],
                )

    def test_is_gpu_accelerator(self) -> None:
        for case in self.cases["is_gpu_accelerator"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    is_gpu_accelerator(case.get("io_class")),
                )

    def test_unique_gpu_devices(self) -> None:
        for case in self.cases["unique_gpu_devices"]:
            with self.subTest(name=case["name"]):
                devices = [GpuDevice(**device) for device in case["devices"]]
                unique_devices = unique_gpu_devices(devices)
                self.assertEqual(
                    case["expected"],
                    [
                        {"name": device.name, "util_pct": device.util_pct}
                        for device in unique_devices
                    ],
                )


if __name__ == "__main__":
    unittest.main()
