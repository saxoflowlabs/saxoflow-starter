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

info "Installing OpenSTA from source..."

mkdir -p "$TOOLS_DIR"
cd "$TOOLS_DIR"

check_deps build-essential cmake gcc g++ git tcl-dev swig bison flex zlib1g-dev
sudo apt-get update && sudo apt-get install -y libeigen3-dev

sudo apt-get install -y libreadline-dev

# Ubuntu 24.04 doesn't provide libcudd-dev in the default repos.
# Build and install CUDD from source.
CUDD_DIR="$TOOLS_DIR/cudd"
rm -rf "$CUDD_DIR"
git clone --depth 1 https://github.com/ivmai/cudd.git "$CUDD_DIR"
cd "$CUDD_DIR"
./configure --prefix=/usr/local
make -j"$(nproc)"
sudo make install
cd "$TOOLS_DIR"

clone_or_update https://github.com/The-OpenROAD-Project/OpenSTA.git opensta true

OPENSTA_SRC="$TOOLS_DIR/opensta"
USER_PREFIX="$INSTALL_DIR/opensta"
BIN_DIR_MANAGED="$USER_PREFIX/bin"

rm -rf "$USER_PREFIX"
mkdir -p "$USER_PREFIX"

cd "$OPENSTA_SRC"
mkdir -p build
cd build

cmake .. \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$USER_PREFIX"

cmake --build . -j"$(nproc)"
cmake --install .

chown -R "$(id -u):$(id -g)" "$USER_PREFIX" || true

persist_path_entry "$BIN_DIR_MANAGED" "Added by SaxoFlow OpenSTA installer"

if "$BIN_DIR_MANAGED/sta" -version >/dev/null 2>&1; then
  success "OpenSTA installed successfully to $BIN_DIR_MANAGED"
  info "Detected version: $($BIN_DIR_MANAGED/sta -version 2>&1 | head -1)"
else
  fatal "OpenSTA binary 'sta' was not found after installation"
fi
