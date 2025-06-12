#!/bin/bash

# scripts/common/logger.sh — global logger for SaxoFlow Pro Installer

set -euo pipefail

# Get absolute script dir (robust)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
LOG_DIR="${SCRIPT_DIR}/../logs"
mkdir -p "$LOG_DIR"

# Timestamp generator
timestamp() {
  date +"%Y-%m-%d_%H-%M-%S"
}

# Use calling script basename if TOOL not explicitly set
SCRIPT_NAME="$(basename "${BASH_SOURCE[1]:-installer}")"
LOGFILE="${LOG_DIR}/${TOOL:-$SCRIPT_NAME}-$(timestamp).log"

# Logging functions
info()  { echo -e "\033[1;32m[INFO]\033[0m $*";  echo "[INFO] $*"  >> "$LOGFILE"; }
warn()  { echo -e "\033[1;33m[WARN]\033[0m $*";  echo "[WARN] $*"  >> "$LOGFILE"; }
error() { echo -e "\033[1;31m[ERROR]\033[0m $*"; echo "[ERROR] $*" >> "$LOGFILE"; }

# Global error trap with full context
trap 'error "Script failed at ${BASH_SOURCE[1]}:$LINENO (log: $LOGFILE)"' ERR

export LOGFILE  # Make logfile visible to sub-scripts if needed
