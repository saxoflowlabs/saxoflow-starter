#!/usr/bin/env bash
# saxoflow/scripts/common/logger.sh — Professional unified logger

set -Eeuo pipefail

# Prevent double initialization when sourced multiple times
if [[ "${SAXOFLOW_LOGGER_INITIALIZED:-0}" == "1" ]]; then
  return 0
fi
export SAXOFLOW_LOGGER_INITIALIZED=1

# ------------------------------
# Setup directories
# ------------------------------
LOGGER_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${LOGGER_SCRIPT_DIR}/../logs"
mkdir -p "${LOG_DIR}"

# Who sourced this logger
LOGGER_CALLER="${BASH_SOURCE[1]:-unknown}"
LOGGER_SCRIPT_NAME="$(basename "${LOGGER_CALLER}")"

# Unique logfile per session
LOGFILE="${LOG_DIR}/${LOGGER_SCRIPT_NAME}-$(date +%Y-%m-%d_%H-%M-%S).log"
export LOGFILE

# Use colors only when stdout is a TTY
USE_COLOR=0
if [[ -t 1 ]]; then
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
  echo "${timestamp} ${level}: ${message}" >> "${LOGFILE}"
}

# ------------------------------
# Transcript capture
# ------------------------------
attach_transcript_logging() {
  if [[ "${SAXOFLOW_TRANSCRIPT_ATTACHED:-0}" == "1" ]]; then
    return
  fi
  export SAXOFLOW_TRANSCRIPT_ATTACHED=1

  exec > >(tee -a "${LOGFILE}") 2>&1

  {
    echo "========== SaxoFlow transcript =========="
    echo "Timestamp: $(date +%Y-%m-%d\ %H:%M:%S)"
    echo "Caller: ${LOGGER_CALLER}"
    echo "Script: ${LOGGER_SCRIPT_NAME}"
    echo "Logfile: ${LOGFILE}"
    echo "========================================="
  } >> "${LOGFILE}"
}

# ------------------------------
# Optional debug tracing
# ------------------------------
enable_debug_tracing() {
  if [[ "${SAXOFLOW_DEBUG:-0}" == "1" ]]; then
    export PS4='+ ${BASH_SOURCE##*/}:${LINENO}: '
    set -x
  fi
}

# ------------------------------
# Public log functions
# ------------------------------
info() {
  if [[ "${USE_COLOR}" -eq 1 ]]; then
    echo -e "\033[1;34mINFO:    $1\033[0m"
  else
    echo "INFO:    $1"
  fi
  _log "INFO" "$1"
}

note() {
  if [[ "${USE_COLOR}" -eq 1 ]]; then
    echo -e "\033[1;36mNOTE:    $1\033[0m"
  else
    echo "NOTE:    $1"
  fi
  _log "NOTE" "$1"
}

warning() {
  if [[ "${USE_COLOR}" -eq 1 ]]; then
    echo -e "\033[1;33mWARNING: $1\033[0m"
  else
    echo "WARNING: $1"
  fi
  _log "WARN" "$1"
}

warn() {
  warning "$1"
}

error() {
  if [[ "${USE_COLOR}" -eq 1 ]]; then
    echo -e "\033[1;31mERROR:   $1\033[0m"
  else
    echo "ERROR:   $1"
  fi
  _log "ERROR" "$1"
}

success() {
  if [[ "${USE_COLOR}" -eq 1 ]]; then
    echo -e "\033[1;32mSUCCESS: $1\033[0m"
  else
    echo "SUCCESS: $1"
  fi
  _log "SUCCESS" "$1"
}

fatal() {
  local msg="$1"

  if [[ "${USE_COLOR}" -eq 1 ]]; then
    echo -e "\033[1;31mERROR:   ${msg}\033[0m" >&2
  else
    echo "ERROR:   ${msg}" >&2
  fi

  _log "FATAL" "${msg}"

  echo "Log: ${LOGFILE}" >&2
  echo "---- last 120 log lines ----" >&2
  tail -n 120 "${LOGFILE}" >&2 || true
  exit 1
}

# ------------------------------
# Detailed ERR trap
# ------------------------------
_saxoflow_err_trap() {
  local exit_code="$?"
  local failed_command="${BASH_COMMAND}"

  # In an ERR trap:
  #   BASH_SOURCE[0] = this file
  #   BASH_SOURCE[1] = script/function where trap is active
  #   BASH_LINENO[0] = line in BASH_SOURCE[1] that triggered the error
  local src="${BASH_SOURCE[1]:-${LOGGER_CALLER}}"
  local line="${BASH_LINENO[0]:-unknown}"
  local func="${FUNCNAME[1]:-main}"

  local msg
  msg="Command failed with exit code ${exit_code} at ${src}:${line} in ${func}(): ${failed_command}"

  if [[ "${USE_COLOR}" -eq 1 ]]; then
    echo -e "\033[1;31mERROR:   ${msg}\033[0m" >&2
  else
    echo "ERROR:   ${msg}" >&2
  fi

  _log "FATAL" "${msg}"

  echo "Log: ${LOGFILE}" >&2
  echo "---- last 120 log lines ----" >&2
  tail -n 120 "${LOGFILE}" >&2 || true

  exit "${exit_code}"
}

# ------------------------------
# Initialize logging
# ------------------------------
attach_transcript_logging
enable_debug_tracing

# Ensure ERR trap propagates through functions, subshells, command substitutions
set -o errtrace

trap '_saxoflow_err_trap' ERR