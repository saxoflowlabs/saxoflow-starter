#!/bin/bash

# saxoflow/common/check_deps.sh — system package dependency manager (APT-based)

set -euo pipefail

# Always resolve absolute path for logger import
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$SCRIPT_DIR/logger.sh"

APT_UPDATED=0

# Check and install single APT package
check_and_install() {
    local pkg="$1"
    if ! dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "ok installed"; then
        info "📦 Installing missing dependency: $pkg"
        if [ "$APT_UPDATED" -eq 0 ]; then
            sudo apt update
            APT_UPDATED=1
        fi
        sudo apt install -y "$pkg"
    else
        info "✅ Dependency already installed: $pkg"
    fi
}

# Main entrypoint: batch check multiple packages
check_deps() {
    info "🔍 Checking APT package dependencies..."
    for pkg in "$@"; do
        check_and_install "$pkg"
    done
}
