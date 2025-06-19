#!/bin/bash

# saxoflow/scripts/common/check_deps.sh — Universal system package dependency manager (APT-based)

set -euo pipefail

# Resolve path for logger import
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$SCRIPT_DIR/logger.sh"

APT_UPDATED=0

# --------------------------
# Internal helper: install one APT package
# --------------------------
check_and_install() {
    local pkg="$1"

    if ! dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "ok installed"; then
        info "📦 Missing dependency: $pkg"
        if [ "$APT_UPDATED" -eq 0 ]; then
            info "🔄 Updating APT package index..."
            sudo apt-get update -qq
            APT_UPDATED=1
        fi
        sudo apt-get install -y "$pkg"
        info "✅ Installed: $pkg"
    else
        info "✅ Dependency already present: $pkg"
    fi
}

# --------------------------
# Public API: batch check multiple dependencies
# Usage: check_deps package1 package2 package3 ...
# --------------------------
check_deps() {
    info "🔍 Checking system dependencies..."
    for pkg in "$@"; do
        check_and_install "$pkg"
    done
}
