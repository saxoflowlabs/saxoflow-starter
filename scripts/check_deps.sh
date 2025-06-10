#!/bin/bash
# Reusable script to check and install required dependencies

set -e

APT_UPDATED=0

check_and_install() {
    local pkg="$1"
    if ! dpkg -s "$pkg" &>/dev/null; then
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

check_deps() {
    echo "🔍 Checking dependencies..."
    for pkg in "$@"; do
        check_and_install "$pkg"
    done
}
