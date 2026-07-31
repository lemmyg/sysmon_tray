"""Unit tests for sysmon_tray sensor helpers."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from ..sensors import (
    SensorSnapshot,
    format_battery_tray_part,
    format_memory_tooltip,
    format_memory_tray_part,
    format_metric_pair_tray_part,
    format_tooltip,
    format_tray_label,
    memory_bytes_to_gb,
    memory_bytes_to_gb_pair,
    memory_speculative_bytes,
    memory_used_bytes_from_stats,
)
from ..smc_darwin import decode_smc_value, smc_key_to_uint


def _load_cases() -> dict:
    fixture_path = Path(__file__).with_suffix(".yaml")
    with fixture_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


class TestSensors(unittest.TestCase):
    """Validate formatting and SMC decoding helpers."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = _load_cases()

    def test_format_tray_label(self) -> None:
        for case in self.cases["format_tray_label"]:
            with self.subTest(name=case["name"]):
                snapshot = SensorSnapshot(**case["snapshot"])
                components = case.get("components")
                if components is None:
                    label = format_tray_label(snapshot)
                else:
                    label = format_tray_label(snapshot, components)
                self.assertEqual(case["expected"], label)

    def test_format_metric_pair_tray_part(self) -> None:
        for case in self.cases["format_metric_pair_tray_part"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    format_metric_pair_tray_part(
                        case["prefix"],
                        case.get("first_value"),
                        case["first_suffix"],
                        case["show_first"],
                        case.get("second_value"),
                        case["second_suffix"],
                        case["show_second"],
                    ),
                )

    def test_format_battery_tray_part(self) -> None:
        for case in self.cases["format_battery_tray_part"]:
            with self.subTest(name=case["name"]):
                snapshot = SensorSnapshot(**case["snapshot"])
                self.assertEqual(
                    case["expected"],
                    format_battery_tray_part(
                        snapshot,
                        show_power=case["show_power"],
                        show_pct=case["show_pct"],
                    ),
                )

    def test_format_tooltip(self) -> None:
        for case in self.cases["format_tooltip"]:
            with self.subTest(name=case["name"]):
                snapshot = SensorSnapshot(**case["snapshot"])
                tooltip = format_tooltip(snapshot)
                for expected in case["expected_contains"]:
                    self.assertIn(expected, tooltip)

    def test_decode_smc_value(self) -> None:
        for case in self.cases["decode_smc_value"]:
            with self.subTest(name=case["name"]):
                raw = bytes.fromhex(case["raw_hex"])
                value = decode_smc_value(raw, case["data_type"], case["data_size"])
                self.assertIsNotNone(value)
                self.assertAlmostEqual(case["expected"], value, places=4)

    def test_smc_key_to_uint(self) -> None:
        for case in self.cases["smc_key_to_uint"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(case["expected"], smc_key_to_uint(case["key"]))

    def test_memory_speculative_bytes(self) -> None:
        for case in self.cases["memory_speculative_bytes"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    memory_speculative_bytes(
                        case.get("memory_available"),
                        case.get("memory_free"),
                        case.get("memory_inactive"),
                    ),
                )

    def test_memory_used_bytes_from_stats(self) -> None:
        for case in self.cases["memory_used_bytes_from_stats"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    memory_used_bytes_from_stats(
                        case.get("memory_used"),
                        case.get("memory_available"),
                        case.get("memory_free"),
                        case.get("memory_inactive"),
                    ),
                )

    def test_memory_bytes_to_gb(self) -> None:
        for case in self.cases["memory_bytes_to_gb"]:
            with self.subTest(name=case["name"]):
                self.assertAlmostEqual(
                    case["expected"],
                    memory_bytes_to_gb(case["memory_bytes"]),
                    places=4,
                )

    def test_memory_bytes_to_gb_pair(self) -> None:
        for case in self.cases["memory_bytes_to_gb_pair"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    tuple(case["expected"]),
                    memory_bytes_to_gb_pair(case["used_bytes"], case["total_bytes"]),
                )

    def test_format_memory_tray_part(self) -> None:
        for case in self.cases["format_memory_tray_part"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    format_memory_tray_part(
                        case.get("memory_used_gb"),
                        case.get("memory_total_gb"),
                        show_gb=case.get("show_gb", True),
                        show_pct=case.get("show_pct", True),
                    ),
                )

    def test_format_memory_tooltip(self) -> None:
        for case in self.cases["format_memory_tooltip"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    format_memory_tooltip(
                        case.get("memory_used_gb"),
                        case.get("memory_total_gb"),
                    ),
                )


if __name__ == "__main__":
    unittest.main()
