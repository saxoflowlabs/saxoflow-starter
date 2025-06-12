#!/bin/bash

set -euo pipefail

APT_UPDATED=0

# Function to check if a package is installed, and install if missing
check_and_install() {
    local pkg="$1"
    if ! dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "ok installed"; then
        echo "📦 Installing missing dependency: $pkg"
        if [ "$APT_UPDATED" -eq 0 ]; then
            sudo apt update
            APT_UPDATED=1
        fi
        sudo apt install -y "$pkg"
    else
        echo "✅ Dependency already installed: $pkg"
    fi
}

# Function to check multiple packages in batch
check_deps() {
    echo "🔍 Checking APT package dependencies..."
    for pkg in "$@"; do
        check_and_install "$pkg"
    done
}
