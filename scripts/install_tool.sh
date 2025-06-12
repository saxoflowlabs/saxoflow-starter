#!/bin/bash

set -e

# Resolve root path absolutely
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

TOOL="$1"
if [ -z "$TOOL" ]; then
  echo "Usage: $0 <tool>"
  exit 1
fi

# Load helpers
source "$ROOT_DIR/scripts/common/logger.sh"
source "$ROOT_DIR/scripts/common/paths.sh"

# Resolve recipe path
RECIPE="$ROOT_DIR/scripts/recipes/${TOOL}.sh"

if [ ! -f "$RECIPE" ]; then
  error "No recipe found for tool: $TOOL"
  exit 1
fi

info "🚀 Starting installation for $TOOL..."
bash "$RECIPE"
info "✅ Installation complete for $TOOL"
