"""Unit tests for macOS system power helpers."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from ..power_darwin import (
    battery_discharge_w,
    battery_percent,
    format_battery_pct_part,
    format_battery_power_part,
    milliwatts_to_watts,
)


def _load_cases() -> dict:
    fixture_path = Path(__file__).with_suffix(".yaml")
    with fixture_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


class TestPowerDarwin(unittest.TestCase):
    """Validate power conversion helpers."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = _load_cases()

    def test_battery_discharge_w(self) -> None:
        for case in self.cases["battery_discharge_w"]:
            with self.subTest(name=case["name"]):
                self.assertAlmostEqual(
                    case["expected"],
                    battery_discharge_w(
                        case["battery_power_w"],
                        case["system_power_w"],
                        case["external_connected"],
                    ),
                    places=4,
                )

    def test_format_battery_power_part(self) -> None:
        for case in self.cases["format_battery_power_part"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    format_battery_power_part(
                        case["battery_power_w"],
                        case["external_connected"],
                        case.get("system_power_w"),
                    ),
                )

    def test_battery_percent(self) -> None:
        for case in self.cases["battery_percent"]:
            with self.subTest(name=case["name"]):
                result = battery_percent(
                    case["current_capacity"],
                    case["max_capacity"],
                )
                if case["expected"] is None:
                    self.assertIsNone(result)
                else:
                    self.assertAlmostEqual(case["expected"], result, places=4)

    def test_format_battery_pct_part(self) -> None:
        for case in self.cases["format_battery_pct_part"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    format_battery_pct_part(case["battery_pct"]),
                )

    def test_milliwatts_to_watts(self) -> None:
        for case in self.cases["milliwatts_to_watts"]:
            with self.subTest(name=case["name"]):
                self.assertAlmostEqual(
                    case["expected"],
                    milliwatts_to_watts(case["milliwatts"]),
                    places=4,
                )


if __name__ == "__main__":
    unittest.main()
