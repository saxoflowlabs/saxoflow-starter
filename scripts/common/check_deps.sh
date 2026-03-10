#!/usr/bin/env bash

# saxoflow/scripts/common/check_deps.sh
# Universal system package dependency manager (APT-based)

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/logger.sh"

APT_UPDATED=0

apt_update_once() {
    if [[ "${APT_UPDATED}" -eq 0 ]]; then
        info "Updating APT package index..."
        sudo apt-get update -qq
        APT_UPDATED=1
    fi
}

apt_package_installed() {
    local pkg="$1"
    dpkg-query -W -f='${Status}' "${pkg}" 2>/dev/null | grep -q "ok installed"
}

apt_package_available() {
    local pkg="$1"

    apt_update_once

    # apt-cache show returns nonzero when package is unknown
    apt-cache show "${pkg}" >/dev/null 2>&1
}

check_and_install() {
    local pkg="$1"

    if apt_package_installed "${pkg}"; then
        note "Dependency already present: ${pkg}"
        return 0
    fi

    warning "Missing dependency: ${pkg}"

    if ! apt_package_available "${pkg}"; then
        fatal "APT package '${pkg}' is not available on this system. Do not list source-built dependencies in check_deps; install them inside the recipe instead."
    fi

    sudo apt-get install -y "${pkg}"
    success "Installed: ${pkg}"
}

check_and_install_optional() {
    local pkg="$1"

    if apt_package_installed "${pkg}"; then
        note "Optional dependency already present: ${pkg}"
        return 0
    fi

    warning "Missing optional dependency: ${pkg}"

    if ! apt_package_available "${pkg}"; then
        warning "Optional APT package '${pkg}' is not available on this system. Skipping."
        return 0
    fi

    sudo apt-get install -y "${pkg}"
    success "Installed optional dependency: ${pkg}"
}

# Public API: required packages
# Usage: check_deps pkg1 pkg2 pkg3
check_deps() {
    info "Checking required system dependencies..."
    local pkg
    for pkg in "$@"; do
        check_and_install "${pkg}"
    done
}

# Public API: optional packages
# Usage: check_optional_deps pkg1 pkg2
check_optional_deps() {
    info "Checking optional system dependencies..."
    local pkg
    for pkg in "$@"; do
        check_and_install_optional "${pkg}"
    done
}