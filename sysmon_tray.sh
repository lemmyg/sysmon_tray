#!/usr/bin/env bash
# Start, stop, or restart sysmon_tray outside the current process tree
# (survives closing Cursor / the terminal).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GIT_PARENT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON="${SCRIPT_DIR}/.venv/bin/python"
PROCESS_NAME="sysmon_tray"
LOG_FILE="${SYSMON_TRAY_LOG:-/tmp/sysmon_tray.log}"
REFRESH_SECONDS="${SYSMON_TRAY_REFRESH_SECONDS:-5.0}"

usage() {
  echo "Usage: $0 {start|stop|restart|status}" >&2
  echo "Env: SYSMON_TRAY_REFRESH_SECONDS (default: 5.0)" >&2
  echo "     SYSMON_TRAY_LOG (default: /tmp/sysmon_tray.log)" >&2
  exit 1
}

is_running() {
  pgrep -x "${PROCESS_NAME}" >/dev/null 2>&1
}

pid_of() {
  pgrep -x "${PROCESS_NAME}" || true
}

cmd_start() {
  if is_running; then
    echo "${PROCESS_NAME} already running (pid $(pid_of))"
    return 0
  fi
  if [[ ! -x "${PYTHON}" ]]; then
    echo "Missing venv python: ${PYTHON}" >&2
    exit 1
  fi

  # Launch via osascript so the process is not a child of Cursor/the terminal.
  local runner
  runner="$(mktemp "${TMPDIR:-/tmp}/sysmon_tray_start.XXXXXX")"
  cat >"${runner}" <<EOF
#!/bin/bash
export PYTHONPATH="${GIT_PARENT}:\${PYTHONPATH:-}"
nohup "${PYTHON}" -m sysmon_tray --refresh-seconds "${REFRESH_SECONDS}" \\
  >>"${LOG_FILE}" 2>&1 </dev/null &
disown
EOF
  chmod +x "${runner}"

  osascript -e "do shell script \"bash $(printf %q "${runner}"); rm -f $(printf %q "${runner}")\"" >/dev/null
  sleep 1

  if is_running; then
    echo "started ${PROCESS_NAME} (pid $(pid_of), refresh ${REFRESH_SECONDS}s)"
  else
    echo "failed to start ${PROCESS_NAME}; see ${LOG_FILE}" >&2
    exit 1
  fi
}

cmd_stop() {
  if ! is_running; then
    echo "${PROCESS_NAME} is not running"
    return 0
  fi
  local pids
  pids="$(pid_of)"
  pkill -x "${PROCESS_NAME}" || true
  # Also clear any Cursor-attached python -m launches that never renamed.
  pkill -f "${PYTHON} -m sysmon_tray" 2>/dev/null || true
  sleep 0.5
  if is_running; then
    echo "failed to stop ${PROCESS_NAME} (pid $(pid_of))" >&2
    exit 1
  fi
  echo "stopped ${PROCESS_NAME} (was pid ${pids})"
}

cmd_restart() {
  cmd_stop
  cmd_start
}

cmd_status() {
  if is_running; then
    echo "${PROCESS_NAME} running (pid $(pid_of))"
  else
    echo "${PROCESS_NAME} not running"
    exit 1
  fi
}

case "${1:-}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  restart) cmd_restart ;;
  status) cmd_status ;;
  *) usage ;;
esac
