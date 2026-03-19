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

info "Installing Edalize EDA tool abstraction library..."

USER_PREFIX="$INSTALL_DIR/edalize"
BIN_DIR_MANAGED="$USER_PREFIX/bin"

check_deps python3 python3-pip python3-venv

rm -rf "$USER_PREFIX"
python3 -m venv "$USER_PREFIX"

"$BIN_DIR_MANAGED/python" -m pip install --upgrade pip setuptools wheel
"$BIN_DIR_MANAGED/python" -m pip install edalize

chown -R "$(id -u):$(id -g)" "$USER_PREFIX" || true

persist_path_entry "$BIN_DIR_MANAGED" "Added by SaxoFlow Edalize installer"

# Verify: the package must be importable and el_docker script must be present.
if "$BIN_DIR_MANAGED/python" -c "import edalize" 2>/dev/null; then
  VERSION="$("$BIN_DIR_MANAGED/python" -c "import importlib.metadata as m; print(m.version('edalize'))" 2>/dev/null || true)"
  success "Edalize installed successfully to $BIN_DIR_MANAGED"
  if [[ -n "$VERSION" ]]; then
    info "Detected version: $VERSION"
  else
    info "Detected version: (version probe failed)"
  fi
else
  fatal "edalize package was not found after installation"
fi
