#!/bin/bash

set -e

# Load global paths and helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$ROOT_DIR/scripts/common/logger.sh"
source "$ROOT_DIR/scripts/common/paths.sh"
source "$ROOT_DIR/scripts/common/check_deps.sh"

LOG_FILE="$ROOT_DIR/bootstrap.log"
info "🚀 SaxoFlow Bootstrap Started"
echo "Log: $LOG_FILE"

# Create essential directories (safe to run multiple times)
mkdir -p "$TOOLS_DIR"

# Parse CLI arguments
usage() {
  echo "Usage: $0 [all | verilator | symbiyosys | nextpnr | openroad | vscode]"
  exit 1
}

if [ $# -eq 0 ]; then
  usage
fi

# Dispatcher to recipes
for tool in "$@"; do
  case "$tool" in
    all)
      "$ROOT_DIR/scripts/recipes/verilator.sh"
      "$ROOT_DIR/scripts/recipes/symbiyosys.sh"
      "$ROOT_DIR/scripts/recipes/nextpnr.sh"
      "$ROOT_DIR/scripts/recipes/openroad.sh"
      "$ROOT_DIR/scripts/recipes/vscode.sh"
      ;;
    verilator)
      "$ROOT_DIR/scripts/recipes/verilator.sh"
      ;;
    symbiyosys)
      "$ROOT_DIR/scripts/recipes/symbiyosys.sh"
      ;;
    nextpnr)
      "$ROOT_DIR/scripts/recipes/nextpnr.sh"
      ;;
    openroad)
      "$ROOT_DIR/scripts/recipes/openroad.sh"
      ;;
    vscode)
      "$ROOT_DIR/scripts/recipes/vscode.sh"
      ;;
    *)
      error "Unknown tool: $tool"
      usage
      ;;
  esac
done

info "✅ SaxoFlow Bootstrap Complete"
