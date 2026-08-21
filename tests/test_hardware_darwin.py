"""Unit tests for macOS hardware model helpers."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

import yaml

from .. import hardware_darwin
from ..hardware_darwin import (
    DiskHardware,
    HardwareInfo,
    chip_name_from_overview,
    cpu_cores_from_number_processors,
    disk_from_controller_entry,
    disk_from_storage_entry,
    disk_hardware_from_controllers,
    disk_hardware_from_profiler_payload,
    disk_hardware_from_storage,
    disk_medium_label,
    flatten_profiler_items,
    gpu_hardware_from_displays,
    hardware_info_from_profiler_payload,
    hardware_overview_from_payload,
    is_profiler_no,
    is_profiler_yes,
    machine_model_from_overview,
    merge_disk_hardware,
    optional_positive_int,
    optional_stripped_text,
    read_hardware_info,
)


def _load_cases() -> dict:
    fixture_path = Path(__file__).with_suffix(".yaml")
    with fixture_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _disk_as_dict(disk: DiskHardware | None) -> dict | None:
    if disk is None:
        return None
    return {
        "name": disk.name,
        "medium": disk.medium,
        "size_bytes": disk.size_bytes,
    }


def _disk_from_case(raw: dict | None) -> DiskHardware | None:
    if raw is None:
        return None
    return DiskHardware(**raw)


def _hardware_info_as_dict(info: HardwareInfo) -> dict:
    return {
        "machine_model": info.machine_model,
        "chip_name": info.chip_name,
        "cpu_cores": info.cpu_cores,
        "gpus": [
            {"name": gpu.name, "core_count": gpu.core_count}
            for gpu in info.gpus
        ],
        "disk": _disk_as_dict(info.disk),
    }


class TestHardwareDarwin(unittest.TestCase):
    """Validate laptop model parsing for the tray tooltip."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = _load_cases()

    def test_optional_stripped_text(self) -> None:
        for case in self.cases["optional_stripped_text"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    optional_stripped_text(case.get("value")),
                )

    def test_optional_positive_int(self) -> None:
        for case in self.cases["optional_positive_int"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    optional_positive_int(case.get("value")),
                )

    def test_machine_model_from_overview(self) -> None:
        for case in self.cases["machine_model_from_overview"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    machine_model_from_overview(case["overview"]),
                )

    def test_chip_name_from_overview(self) -> None:
        for case in self.cases["chip_name_from_overview"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    chip_name_from_overview(case["overview"]),
                )

    def test_cpu_cores_from_number_processors(self) -> None:
        for case in self.cases["cpu_cores_from_number_processors"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    cpu_cores_from_number_processors(case.get("value")),
                )

    def test_gpu_hardware_from_displays(self) -> None:
        for case in self.cases["gpu_hardware_from_displays"]:
            with self.subTest(name=case["name"]):
                gpus = gpu_hardware_from_displays(case["entries"])
                self.assertEqual(
                    case["expected"],
                    [
                        {"name": gpu.name, "core_count": gpu.core_count}
                        for gpu in gpus
                    ],
                )

    def test_hardware_overview_from_payload(self) -> None:
        for case in self.cases["hardware_overview_from_payload"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    hardware_overview_from_payload(case["payload"]),
                )

    def test_hardware_info_from_profiler_payload(self) -> None:
        for case in self.cases["hardware_info_from_profiler_payload"]:
            with self.subTest(name=case["name"]):
                info = hardware_info_from_profiler_payload(case["payload"])
                self.assertEqual(
                    case["expected"],
                    _hardware_info_as_dict(info),
                )

    def test_read_hardware_info(self) -> None:
        for case in self.cases["read_hardware_info"]:
            with self.subTest(name=case["name"]):
                hardware_darwin._cached_hardware_info = None
                hardware_darwin._hardware_info_loaded = False
                if "stdout_json" in case:
                    stdout = json.dumps(case["stdout_json"]).encode()
                else:
                    stdout = case["stdout"].encode()
                with mock.patch.object(
                    hardware_darwin.subprocess,
                    "check_output",
                    return_value=stdout,
                ):
                    info = read_hardware_info()
                self.assertEqual(case["expected"], _hardware_info_as_dict(info))

    def test_is_profiler_yes(self) -> None:
        for case in self.cases["is_profiler_yes"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    is_profiler_yes(case.get("value")),
                )

    def test_is_profiler_no(self) -> None:
        for case in self.cases["is_profiler_no"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    is_profiler_no(case.get("value")),
                )

    def test_flatten_profiler_items(self) -> None:
        for case in self.cases["flatten_profiler_items"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    flatten_profiler_items(case["entries"]),
                )

    def test_disk_medium_label(self) -> None:
        for case in self.cases["disk_medium_label"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    disk_medium_label(case.get("medium_type")),
                )

    def test_disk_from_controller_entry(self) -> None:
        for case in self.cases["disk_from_controller_entry"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    _disk_as_dict(disk_from_controller_entry(case["entry"])),
                )

    def test_disk_from_storage_entry(self) -> None:
        for case in self.cases["disk_from_storage_entry"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    _disk_as_dict(disk_from_storage_entry(case["entry"])),
                )

    def test_merge_disk_hardware(self) -> None:
        for case in self.cases["merge_disk_hardware"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    _disk_as_dict(
                        merge_disk_hardware(
                            _disk_from_case(case.get("left")),
                            _disk_from_case(case.get("right")),
                        )
                    ),
                )

    def test_disk_hardware_from_controllers(self) -> None:
        for case in self.cases["disk_hardware_from_controllers"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    _disk_as_dict(disk_hardware_from_controllers(case["entries"])),
                )

    def test_disk_hardware_from_storage(self) -> None:
        for case in self.cases["disk_hardware_from_storage"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    _disk_as_dict(disk_hardware_from_storage(case["entries"])),
                )

    def test_disk_hardware_from_profiler_payload(self) -> None:
        for case in self.cases["disk_hardware_from_profiler_payload"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(
                    case["expected"],
                    _disk_as_dict(
                        disk_hardware_from_profiler_payload(case["payload"])
                    ),
                )


if __name__ == "__main__":
    unittest.main()
