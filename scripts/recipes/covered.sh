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

info "Installing Covered (Verilog code-coverage analysis tool) from source..."

mkdir -p "$TOOLS_DIR"
cd "$TOOLS_DIR"

check_deps build-essential git autoconf automake libtool \
           libreadline-dev tcl-dev bison flex gperf

clone_or_update https://github.com/chiphackers/covered.git covered false

COVERED_SRC="$TOOLS_DIR/covered"
USER_PREFIX="$INSTALL_DIR/covered"
BIN_DIR_MANAGED="$USER_PREFIX/bin"

rm -rf "$USER_PREFIX"
mkdir -p "$USER_PREFIX"

cd "$COVERED_SRC"

# Covered still uses deprecated direct Tcl_Interp->result access in some
# revisions; patch to Tcl_GetStringResult for compatibility with newer Tcl.
if grep -q "interp->result" src/report.c 2>/dev/null; then
  info "Applying Tcl compatibility patch (interp->result -> Tcl_GetStringResult)..."
  sed -i 's/interp->result/Tcl_GetStringResult(interp)/g' src/report.c
fi

# Bootstrap the autotools build system if configure script is missing
if [[ ! -f configure ]]; then
  info "Bootstrapping autotools..."
  autoreconf -fiv
fi

info "Configuring Covered..."
./configure --prefix="$USER_PREFIX" --disable-debug

info "Building Covered (this may take several minutes)..."
make -j"$(nproc)"
make install

chown -R "$(id -u):$(id -g)" "$USER_PREFIX" || true

persist_path_entry "$BIN_DIR_MANAGED" "Added by SaxoFlow Covered installer"

if "$BIN_DIR_MANAGED/covered" -v >/dev/null 2>&1; then
  success "Covered installed successfully to $BIN_DIR_MANAGED"
  info "Detected version: $($BIN_DIR_MANAGED/covered -v 2>&1 | head -1)"
else
  fatal "covered binary was not found after installation"
fi
