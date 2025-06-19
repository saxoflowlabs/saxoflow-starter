#!/bin/bash

# scripts/common/paths.sh — central installer paths

# Absolute project root directory (2 levels up)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Install destination — all tools installed under ~/.local/ by convention
INSTALL_DIR="$HOME/.local"

# Build sources directory (tools source tree lives here)
TOOLS_DIR="$PROJECT_ROOT/tools-src"

# Export for global use
export PROJECT_ROOT INSTALL_DIR TOOLS_DIR
