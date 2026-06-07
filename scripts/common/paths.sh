#!/bin/bash

# scripts/common/paths.sh — central installer paths

# Absolute project root directory (2 levels up)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Install destination — all tools installed under ~/.local/ by convention
INSTALL_DIR="$HOME/.local"

# Build/download cache must remain writable when SaxoFlow is installed into a
# read-only system site-packages directory.
CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
TOOLS_DIR="${SAXOFLOW_TOOLS_SRC_DIR:-$CACHE_HOME/saxoflow/tools-src}"

# Export for global use
export PROJECT_ROOT INSTALL_DIR TOOLS_DIR CACHE_HOME
