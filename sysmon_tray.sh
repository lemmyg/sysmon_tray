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
LAUNCH_AGENT_LABEL="com.sysmon_tray"
LAUNCH_AGENT_DIR="${HOME}/Library/LaunchAgents"
LAUNCH_AGENT_PLIST="${LAUNCH_AGENT_DIR}/${LAUNCH_AGENT_LABEL}.plist"
LEGACY_LAUNCH_AGENT_LABEL="com.galder.sysmon_tray"

usage() {
  echo "Usage: $0 [start|stop|restart|status|install|uninstall]" >&2
  echo "Default with no argument: restart" >&2
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

gui_domain() {
  echo "gui/$(id -u)"
}

bootout_label() {
  local label="$1"
  launchctl bootout "$(gui_domain)/${label}" 2>/dev/null || true
}

write_launch_agent_plist() {
  mkdir -p "${LAUNCH_AGENT_DIR}"
  cat >"${LAUNCH_AGENT_PLIST}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key>
	<string>${LAUNCH_AGENT_LABEL}</string>
	<key>ProgramArguments</key>
	<array>
		<string>${PYTHON}</string>
		<string>-m</string>
		<string>sysmon_tray</string>
		<string>--refresh-seconds</string>
		<string>${REFRESH_SECONDS}</string>
	</array>
	<key>EnvironmentVariables</key>
	<dict>
		<key>PYTHONPATH</key>
		<string>${GIT_PARENT}</string>
	</dict>
	<key>WorkingDirectory</key>
	<string>${SCRIPT_DIR}</string>
	<key>RunAtLoad</key>
	<true/>
	<key>StandardOutPath</key>
	<string>${LOG_FILE}</string>
	<key>StandardErrorPath</key>
	<string>${LOG_FILE}</string>
</dict>
</plist>
EOF
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

cmd_install() {
  if [[ ! -x "${PYTHON}" ]]; then
    echo "Missing venv python: ${PYTHON}" >&2
    exit 1
  fi

  # Drop the old personalized label if present.
  bootout_label "${LEGACY_LAUNCH_AGENT_LABEL}"
  rm -f "${LAUNCH_AGENT_DIR}/${LEGACY_LAUNCH_AGENT_LABEL}.plist"

  bootout_label "${LAUNCH_AGENT_LABEL}"
  write_launch_agent_plist
  launchctl bootstrap "$(gui_domain)" "${LAUNCH_AGENT_PLIST}"
  sleep 1

  if is_running; then
    echo "installed ${LAUNCH_AGENT_LABEL} (pid $(pid_of), plist ${LAUNCH_AGENT_PLIST})"
  else
    echo "installed ${LAUNCH_AGENT_LABEL}, but ${PROCESS_NAME} is not running; see ${LOG_FILE}" >&2
    exit 1
  fi
}

cmd_uninstall() {
  bootout_label "${LAUNCH_AGENT_LABEL}"
  bootout_label "${LEGACY_LAUNCH_AGENT_LABEL}"
  rm -f "${LAUNCH_AGENT_PLIST}"
  rm -f "${LAUNCH_AGENT_DIR}/${LEGACY_LAUNCH_AGENT_LABEL}.plist"
  cmd_stop
  echo "uninstalled ${LAUNCH_AGENT_LABEL}"
}

case "${1:-restart}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  restart) cmd_restart ;;
  status) cmd_status ;;
  install) cmd_install ;;
  uninstall) cmd_uninstall ;;
  *) usage ;;
esac
