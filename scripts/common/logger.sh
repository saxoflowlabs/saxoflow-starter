#!/usr/bin/env bash

# saxoflow/scripts/common/logger.sh — Professional unified logger

set -euo pipefail

# ------------------------------
# Setup directories
# ------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/../logs"
mkdir -p "$LOG_DIR"

# Who sourced this logger (caller script)
CALLER="${BASH_SOURCE[1]:-unknown}"
SCRIPT_NAME="$(basename "$CALLER")"

# Unique logfile per session
LOGFILE="$LOG_DIR/${SCRIPT_NAME}-$(date +%Y-%m-%d_%H-%M-%S).log"
export LOGFILE

# Use colors only when stdout is a TTY (clean when captured by other tools)
USE_COLOR=0
if [ -t 1 ]; then
  USE_COLOR=1
fi

# ------------------------------
# Internal log appender
# ------------------------------
_log() {
  local level="$1"
  local message="$2"
  local timestamp
  timestamp="$(date +"%Y-%m-%d %H:%M:%S")"
  echo "${timestamp} ${level}: ${message}" >> "$LOGFILE"
}

# ------------------------------
# Optional: enable xtrace to logfile when SAXOFLOW_DEBUG=1
# ------------------------------
enable_debug_tracing() {
  if [[ "${SAXOFLOW_DEBUG:-0}" == "1" ]]; then
    # Route xtrace to logfile (fd 3)
    if [[ -n "${LOGFILE:-}" ]]; then
      exec 3>>"$LOGFILE"
      export BASH_XTRACEFD=3
    fi
    export PS4='+ ${BASH_SOURCE##*/}:${LINENO}: '
    set -x
  fi
}

# ------------------------------
# Public log functions (ANSI colors; no emojis)
# Standardized across SaxoFlow: info, note, warning, error, success
# (all colorize BOTH the keyword and the message)
# ------------------------------
info() {
  if [ "$USE_COLOR" -eq 1 ]; then
    echo -e "\033[1;34mINFO:    $1\033[0m"   # Blue
  else
    echo "INFO:    $1"
  fi
  _log "INFO" "$1"
}

note() {
  if [ "$USE_COLOR" -eq 1 ]; then
    echo -e "\033[1;36mNOTE:    $1\033[0m"   # Cyan
  else
    echo "NOTE:    $1"
  fi
  _log "NOTE" "$1"
}

warning() {
  if [ "$USE_COLOR" -eq 1 ]; then
    echo -e "\033[1;33mWARNING: $1\033[0m"   # Yellow
  else
    echo "WARNING: $1"
  fi
  _log "WARN" "$1"
}

# Back-compat alias (some scripts may call warn)
warn() { warning "$1"; }

error() {
  if [ "$USE_COLOR" -eq 1 ]; then
    echo -e "\033[1;31mERROR:   $1\033[0m"   # Red
  else
    echo "ERROR:   $1"
  fi
  _log "ERROR" "$1"
}

success() {
  if [ "$USE_COLOR" -eq 1 ]; then
    echo -e "\033[1;32mSUCCESS: $1\033[0m"   # Green
  else
    echo "SUCCESS: $1"
  fi
  _log "SUCCESS" "$1"
}

# Fatal: red + exit (use for unrecoverable errors)
fatal() {
  if [ "$USE_COLOR" -eq 1 ]; then
    echo -e "\033[1;31mERROR:   $1\033[0m"
  else
    echo "ERROR:   $1"
  fi
  _log "FATAL" "$1"
  echo "See full log at: $LOGFILE"
  exit 1
}

# ------------------------------
# Global trap for unhandled failures
# ------------------------------
trap 'fatal "Script failed at ${CALLER}:${LINENO}"' ERR
