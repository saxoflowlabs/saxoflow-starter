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

info "Installing FuseSoC in a SaxoFlow-managed virtual environment..."

USER_PREFIX="$INSTALL_DIR/fusesoc"
BIN_DIR_MANAGED="$USER_PREFIX/bin"

check_deps python3 python3-pip python3-venv

rm -rf "$USER_PREFIX"
python3 -m venv "$USER_PREFIX"

"$BIN_DIR_MANAGED/python" -m pip install --upgrade pip setuptools wheel
"$BIN_DIR_MANAGED/python" -m pip install fusesoc

chown -R "$(id -u):$(id -g)" "$USER_PREFIX" || true

persist_path_entry "$BIN_DIR_MANAGED" "Added by SaxoFlow FuseSoC installer"

if "$BIN_DIR_MANAGED/fusesoc" --version >/dev/null 2>&1; then
  success "FuseSoC installed successfully to $BIN_DIR_MANAGED"
  info "Detected version: $($BIN_DIR_MANAGED/fusesoc --version)"
else
  fatal "fusesoc binary was not found after installation"
fi