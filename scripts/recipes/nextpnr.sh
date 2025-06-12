#!/bin/bash

set -e
source "$(dirname "$0")/../common/logger.sh"
source "$(dirname "$0")/../common/paths.sh"
source "$(dirname "$0")/../common/check_deps.sh"
source "$(dirname "$0")/../common/clone_or_update.sh"

info "📦 Installing nextpnr + Project IceStorm..."

# ---------------------------------------
# Step 1 — System dependencies
# ---------------------------------------
check_deps \
  cmake g++ pkg-config libboost-all-dev \
  libeigen3-dev qtbase5-dev python3-dev libqt5svg5-dev \
  libftdi-dev libreadline-dev

# ---------------------------------------
# Step 2 — Build IceStorm
# ---------------------------------------
cd "$TOOLS_DIR"
clone_or_update https://github.com/YosysHQ/icestorm.git icestorm

cd icestorm
make -j"$(nproc)"
make install PREFIX="$INSTALL_DIR"
cd "$TOOLS_DIR"

# ---------------------------------------
# Step 3 — Build nextpnr
# ---------------------------------------
clone_or_update https://github.com/YosysHQ/nextpnr.git nextpnr

cd nextpnr
mkdir -p build && cd build

cmake .. \
  -DARCH=ice40 \
  -DCMAKE_INSTALL_PREFIX="$INSTALL_DIR"

make -j"$(nproc)"
make install

info "✅ nextpnr + icestorm fully installed to $INSTALL_DIR/bin"
