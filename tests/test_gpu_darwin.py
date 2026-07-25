"""Unit tests for Intel/macOS GPU utilization helpers."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from ..gpu_darwin import device_utilization_from_performance_statistics


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


if __name__ == "__main__":
    unittest.main()
