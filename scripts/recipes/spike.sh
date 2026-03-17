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

info "Installing Spike (RISC-V ISA simulator) from source..."

mkdir -p "$TOOLS_DIR"
cd "$TOOLS_DIR"

check_deps build-essential cmake git device-tree-compiler \
           libboost-regex-dev libboost-system-dev

clone_or_update https://github.com/riscv-software-src/riscv-isa-sim.git riscv-isa-sim false

SPIKE_SRC="$TOOLS_DIR/riscv-isa-sim"
USER_PREFIX="$INSTALL_DIR/spike"
BIN_DIR_MANAGED="$USER_PREFIX/bin"

rm -rf "$USER_PREFIX"
mkdir -p "$USER_PREFIX"

cd "$SPIKE_SRC"
mkdir -p build
cd build

info "Configuring Spike..."
../configure --prefix="$USER_PREFIX"

info "Building Spike (this may take several minutes)..."
make -j"$(nproc)"
make install

chown -R "$(id -u):$(id -g)" "$USER_PREFIX" || true

persist_path_entry "$BIN_DIR_MANAGED" "Added by SaxoFlow Spike installer"

if "$BIN_DIR_MANAGED/spike" --help >/dev/null 2>&1; then
  success "Spike installed successfully to $BIN_DIR_MANAGED"
  info "Detected version: $($BIN_DIR_MANAGED/spike --help 2>&1 | head -1 || echo '(run spike --help for details)')"
else
  fatal "spike binary was not found after installation"
fi
