"""Unit tests for Apple SMC decoding and fan speed reading."""

from __future__ import annotations

import struct
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from ..smc_darwin import decode_smc_value, read_fan_speeds, smc_key_to_uint


def _load_cases() -> dict:
    fixture_path = Path(__file__).with_suffix(".yaml")
    with fixture_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


class TestSmcDarwin(unittest.TestCase):
    """Validate SMC value decoding and fan enumeration."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = _load_cases()

    def test_smc_key_to_uint(self) -> None:
        for case in self.cases["smc_key_to_uint"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(case["expected"], smc_key_to_uint(case["key"]))

    def test_decode_smc_value(self) -> None:
        for case in self.cases["decode_smc_value"]:
            with self.subTest(name=case["name"]):
                raw = bytes.fromhex(case["raw_hex"])
                data_type = int.from_bytes(case["data_type"].encode(), "big")
                value = decode_smc_value(raw, data_type, case["data_size"])
                if case["expected"] is None:
                    self.assertIsNone(value)
                else:
                    self.assertAlmostEqual(case["expected"], value, places=3)

    def test_read_fan_speeds(self) -> None:
        for case in self.cases["read_fan_speeds"]:
            with self.subTest(name=case["name"]):
                readings = case["readings"]

                def fake_read(_connection: int, key: str, table=readings):
                    return table.get(key)

                with (
                    patch("sysmon_tray.smc_darwin.IOServiceMatching", return_value=1),
                    patch("sysmon_tray.smc_darwin.IOServiceGetMatchingServices", return_value=0),
                    patch("sysmon_tray.smc_darwin.IOIteratorNext", return_value=42),
                    patch("sysmon_tray.smc_darwin.IOServiceOpen", return_value=0),
                    patch("sysmon_tray.smc_darwin.IOServiceClose"),
                    patch("sysmon_tray.smc_darwin._read_smc_key", side_effect=fake_read),
                ):
                    self.assertEqual(case["expected"], read_fan_speeds())


if __name__ == "__main__":
    unittest.main()
