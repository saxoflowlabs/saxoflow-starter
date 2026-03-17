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
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/clone_or_update.sh"

info "Installing Surelog from source..."

mkdir -p "$TOOLS_DIR"
cd "$TOOLS_DIR"

check_deps build-essential cmake gcc g++ git python3 swig bison flex tcl-dev zlib1g-dev libreadline-dev uuid-dev

clone_or_update https://github.com/chipsalliance/Surelog.git surelog true

SURELOG_SRC="$TOOLS_DIR/surelog"
USER_PREFIX="$INSTALL_DIR/surelog"
BIN_DIR_MANAGED="$USER_PREFIX/bin"

rm -rf "$USER_PREFIX"
mkdir -p "$USER_PREFIX"

cd "$SURELOG_SRC"

# UHDM (a Surelog submodule) requires orderedmultidict at CMake configure time.
# Install it into whatever Python CMake will discover (active venv or system).
info "Installing required Python build dependency: orderedmultidict..."
python3 -m pip install --quiet orderedmultidict

mkdir -p build
cd build

cmake .. \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$USER_PREFIX"

cmake --build . -j"$(nproc)"
# antlr4's bundled CMake has an absolute header DESTINATION (/antlr4-runtime)
# behind the "dev" install component. Installing only the default runtime
# component avoids permission errors while still installing surelog binaries.
cmake --install . --component Unspecified

chown -R "$(id -u):$(id -g)" "$USER_PREFIX" || true

persist_path_entry "$BIN_DIR_MANAGED" "Added by SaxoFlow Surelog installer"

if "$BIN_DIR_MANAGED/surelog" --version >/dev/null 2>&1; then
  success "Surelog installed successfully to $BIN_DIR_MANAGED"
  info "Detected version: $($BIN_DIR_MANAGED/surelog --version 2>&1 | head -1)"
else
  fatal "surelog binary was not found after installation"
fi
