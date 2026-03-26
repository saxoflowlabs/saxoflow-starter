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

check_deps build-essential cmake gcc g++ git curl tcl-dev swig bison flex zlib1g-dev
sudo apt-get update && sudo apt-get install -y libeigen3-dev libgtest-dev

sudo apt-get install -y libreadline-dev

OPENSTA_SRC="$TOOLS_DIR/opensta"
USER_PREFIX="$INSTALL_DIR/opensta"
BIN_DIR_MANAGED="$USER_PREFIX/bin"
CUDD_VERSION="3.0.0"
CUDD_TARBALL_URL="https://raw.githubusercontent.com/davidkebo/cudd/main/cudd_versions/cudd-${CUDD_VERSION}.tar.gz"
CUDD_ARCHIVE="$TOOLS_DIR/cudd-${CUDD_VERSION}.tar.gz"
CUDD_SRC_DIR="$TOOLS_DIR/cudd-${CUDD_VERSION}"
CUDD_PREFIX="$USER_PREFIX/cudd"

rm -rf "$USER_PREFIX"
mkdir -p "$USER_PREFIX"

# Ubuntu 24.04 doesn't provide libcudd-dev in the default repos.
# Build and install the documented CUDD 3.0.0 release tarball instead of a
# git checkout, which can trigger stale autotools regeneration targets like
# aclocal-1.14 on modern CI images.
rm -rf "$CUDD_SRC_DIR" "$CUDD_PREFIX"
info "Downloading CUDD ${CUDD_VERSION} release tarball..."
curl -fsSL -o "$CUDD_ARCHIVE" "$CUDD_TARBALL_URL"
tar -xzf "$CUDD_ARCHIVE" -C "$TOOLS_DIR"

cd "$CUDD_SRC_DIR"
./configure --prefix="$CUDD_PREFIX"
make -j"$(nproc)"
make install
cd "$TOOLS_DIR"

clone_or_update https://github.com/The-OpenROAD-Project/OpenSTA.git opensta true

cd "$OPENSTA_SRC"
mkdir -p build
cd build

cmake .. \
  -DCMAKE_BUILD_TYPE=Release \
  -DCUDD_DIR="$CUDD_PREFIX" \
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
