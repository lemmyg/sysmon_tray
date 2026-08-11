# sysmon_tray

<p align="center">
  <img src="docs/widget.png" alt="Menu bar widget" />
</p>

Live CPU/GPU temperature and fan-speed monitor for the macOS menu bar.

The label shows compact readings like `C6%36° G0%36° M19G52% S8W B0W80% F0+ F0+` (CPU %, CPU °C, GPU %, GPU °C, memory, system power W, battery power W / charge %, fan RPMs). Dual-GPU Intel Macs repeat `G` for each GPU. Hover for details; right-click for Refresh interval, Components, and Quit.

## Requirements

- macOS
- Python 3.12+
- `darwin-perf` for temperatures and utilization
- Apple SMC for fan speeds
- PyObjC for the native menu bar
- PySide6 for the refresh timer event loop

## Setup

From the repository root (`sysmon_tray/`):

```bash
curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR="$PWD/.local" sh
export PATH="$PWD/.local:$PATH"
export UV_PYTHON_INSTALL_DIR="$PWD/.local/share/uv/python"
uv venv --python 3.12
uv pip install -r requirements.txt
```

The package is meant to run with `PYTHONPATH` pointing at the parent directory that contains the `sysmon_tray` folder (for example `~/git`):

## Run

Detached (survives closing Cursor or the terminal):

```bash
cd ~/git/sysmon_tray
./sysmon_tray.sh start
./sysmon_tray.sh stop
./sysmon_tray.sh restart
./sysmon_tray.sh status
```

Start at login (writes a machine-local LaunchAgent under `~/Library/LaunchAgents/`; no personal paths are committed in the repo):

```bash
./sysmon_tray.sh install
./sysmon_tray.sh uninstall
```

Optional env vars: `SYSMON_TRAY_REFRESH_SECONDS` (default `5.0`), `SYSMON_TRAY_LOG` (default `/tmp/sysmon_tray.log`).

Foreground (tied to the current shell):

```bash
cd ~/git
export PYTHONPATH="$HOME/git:$PYTHONPATH"
sysmon_tray/.venv/bin/python -m sysmon_tray --refresh-seconds 5.0
```

## Tests

From the parent `git` directory:

```bash
export PYTHONPATH="/path/to/parent/git:$PYTHONPATH"
sysmon_tray/.venv/bin/python -m unittest discover -s sysmon_tray.tests -v
```

## Project layout

| Module | Role |
|--------|------|
| `sysmon_tray.sh` | Detached start / stop / restart / status / install / uninstall |
| `__main__.py` | CLI entry point and process name registration |
| `sensors.py` | macOS sensor reads and label formatting |
| `smc_darwin.py` | Apple SMC fan-speed access |
| `tray_darwin.py` | Native macOS menu bar label |
| `tray_app.py` | Menu bar app, refresh timer, interval options |
