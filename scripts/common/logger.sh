#!/bin/bash

# saxoflow/common/logger.sh — robust logger for SaxoFlow Pro v3.0

set -euo pipefail

# Dynamically resolve absolute directory of this logger script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
LOG_DIR="${SCRIPT_DIR}/../logs"
mkdir -p "$LOG_DIR"

# Timestamp generator
timestamp() {
  date +"%Y-%m-%d_%H-%M-%S"
}

# Derive log filename (tool-aware fallback to calling script)
CALLER="${BASH_SOURCE[1]:-saxoflow}"
SCRIPT_NAME="$(basename "$CALLER")"
LOGFILE="${LOG_DIR}/${TOOL:-$SCRIPT_NAME}-$(timestamp).log"

# Logging helpers (colored output + logfile write)
info()  { echo -e "\033[1;32m[INFO]\033[0m $*";  echo "[INFO] $*"  >> "$LOGFILE"; }
warn()  { echo -e "\033[1;33m[WARN]\033[0m $*";  echo "[WARN] $*"  >> "$LOGFILE"; }
error() { echo -e "\033[1;31m[ERROR]\033[0m $*"; echo "[ERROR] $*" >> "$LOGFILE"; }

# Global error trap with contextual info
trap 'error "Script failed at ${BASH_SOURCE[1]}:$LINENO (log: $LOGFILE)"' ERR

export LOGFILE
