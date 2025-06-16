#!/usr/bin/env bash
set -euo pipefail

# --------------------------------------------------
# logger.sh — simple logging with timestamps & trap
# --------------------------------------------------

# where this file lives
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# where we put logs
LOG_DIR="${SCRIPT_DIR}/../logs"
mkdir -p "$LOG_DIR"

# who sourced us?  (fall back to “unknown” if none)
CALLER="${BASH_SOURCE[1]:-unknown}"
# just the base name for nice log names
SCRIPT_NAME="$(basename "$CALLER")"

# final logfile path
LOGFILE="$LOG_DIR/${SCRIPT_NAME}-$(date +%Y-%m-%d_%H-%M-%S).log"
export LOGFILE

# append to the logfile
_log() {
  echo "$1" >> "$LOGFILE"
}

info() {
  echo -e "ℹ️  $1"
  _log "INFO: $1"
}

warn() {
  echo -e "⚠️  $1"
  _log "WARN: $1"
}

error() {
  echo -e "❌ $1"
  _log "ERROR: $1"
  echo "▶️ See full log at $LOGFILE"
  exit 1
}

# trap any error anywhere and report with our caller name
#trap 'error "Script failed at ${CALLER}:${LINENO} (see log)"' ERR
