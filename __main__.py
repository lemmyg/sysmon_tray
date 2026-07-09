"""Run the system tray monitor."""

from __future__ import annotations

import argparse
import sys
import setproctitle
from .tray_app import TrayMonitorApp

PROCESS_NAME = "sysmon_tray"

def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(description="macOS menu bar temperature and fan monitor")
    parser.add_argument(
        "--refresh-seconds",
        type=float,
        default=5.0,
        help="Polling interval in seconds (default: 5.0)",
    )
    return parser


def main() -> int:
    """Entry point for ``python -m sysmon_tray``."""
    setproctitle.setproctitle(PROCESS_NAME)
    args = build_parser().parse_args()
    if args.refresh_seconds <= 0:
        raise SystemExit("--refresh-seconds must be greater than zero")
    app = TrayMonitorApp(refresh_seconds=args.refresh_seconds)
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
