#!/usr/bin/env bash

set -Eeuo pipefail

# shellcheck source=/dev/null
source "$(dirname "$0")/../common/logger.sh"
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/paths.sh"
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/persist_path.sh"
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/check_deps.sh"

info "Installing cocotb in a SaxoFlow-managed virtual environment..."

USER_PREFIX="$INSTALL_DIR/cocotb"
BIN_DIR_MANAGED="$USER_PREFIX/bin"

check_deps python3 python3-pip python3-venv

rm -rf "$USER_PREFIX"
python3 -m venv "$USER_PREFIX"

"$BIN_DIR_MANAGED/python" -m pip install --upgrade pip setuptools wheel
"$BIN_DIR_MANAGED/python" -m pip install cocotb

chown -R "$(id -u):$(id -g)" "$USER_PREFIX" || true

persist_path_entry "$BIN_DIR_MANAGED" "Added by SaxoFlow cocotb installer"

if "$BIN_DIR_MANAGED/cocotb-config" --version >/dev/null 2>&1; then
  success "cocotb installed successfully to $BIN_DIR_MANAGED"
  info "Detected version: $($BIN_DIR_MANAGED/cocotb-config --version)"
else
  fatal "cocotb-config was not found after installation"
fi