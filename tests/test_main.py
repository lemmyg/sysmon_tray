"""Unit tests for sysmon_tray entry point helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

import yaml

from .. import __main__ as main_module


def _load_cases() -> dict:
    fixture_path = Path(__file__).with_suffix(".yaml")
    with fixture_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


class TestMain(unittest.TestCase):
    """Validate CLI entry point helpers."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = _load_cases()

    def test_main(self) -> None:
        for case in self.cases["main"]:
            with self.subTest(name=case["name"]):
                tray_app = mock.MagicMock()
                tray_app.run.return_value = case["expected_exit"]
                with mock.patch.object(
                    main_module.setproctitle,
                    "setproctitle",
                ) as fake_setproctitle, mock.patch.object(
                    main_module,
                    "TrayMonitorApp",
                    return_value=tray_app,
                ) as tray_app_cls, mock.patch.object(
                    sys,
                    "argv",
                    case["argv"],
                ):
                    exit_code = main_module.main()
                fake_setproctitle.assert_called_once_with(main_module.PROCESS_NAME)
                tray_app_cls.assert_called_once_with(refresh_seconds=case["refresh_seconds"])
                self.assertEqual(case["expected_exit"], exit_code)


if __name__ == "__main__":
    unittest.main()
