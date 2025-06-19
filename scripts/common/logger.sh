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
# Public log functions
# ------------------------------
info() {
    echo -e "\033[1;34mℹ️  $1\033[0m"   # Blue for info
    _log "INFO" "$1"
}

warn() {
    echo -e "\033[1;33m⚠️  $1\033[0m"   # Yellow for warnings
    _log "WARN" "$1"
}

error() {
    echo -e "\033[1;31m❌ $1\033[0m"    # Red for errors
    _log "ERROR" "$1"
    echo "▶️ See full log at: $LOGFILE"
    exit 1
}

# ------------------------------
# Global trap for unhandled failures
# ------------------------------
trap 'error "Script failed at ${CALLER}:${LINENO} (see full log: $LOGFILE)"' ERR
