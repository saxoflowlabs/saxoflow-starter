#!/bin/bash

set -e
set -xuo pipefail

source "$(dirname "$0")/../common/logger.sh"
source "$(dirname "$0")/../common/paths.sh"
source "$(dirname "$0")/../common/check_deps.sh"
source "$(dirname "$0")/../common/clone_or_update.sh"

info "📦 Installing nextpnr + Project IceStorm..."

# ✅ Ensure tools dir exists
mkdir -p "$TOOLS_DIR"
cd "$TOOLS_DIR"

# --------------------------------------------------
# Step 1 — Dependencies (system packages only)
# --------------------------------------------------
check_deps \
  cmake g++ pkg-config libboost-all-dev \
  libeigen3-dev qtbase5-dev python3-dev libqt5svg5-dev \
  libftdi-dev libreadline-dev

# --------------------------------------------------
# Step 2 — Build IceStorm (dependency for nextpnr)
# --------------------------------------------------
clone_or_update https://github.com/YosysHQ/icestorm.git icestorm

cd icestorm

# ✅ SaxoFlow-controlled IceStorm install location
ICESTORM_PREFIX="$INSTALL_DIR/icestorm"
mkdir -p "$ICESTORM_PREFIX"

make -j"$(nproc)"
make install PREFIX="$ICESTORM_PREFIX"
cd "$TOOLS_DIR"

# --------------------------------------------------
# Step 3 — Build nextpnr with IceStorm linked
# --------------------------------------------------
clone_or_update https://github.com/YosysHQ/nextpnr.git nextpnr

cd nextpnr
mkdir -p build && cd build

# ✅ SaxoFlow-controlled nextpnr install location
NEXTPNR_PREFIX="$INSTALL_DIR/nextpnr"
mkdir -p "$NEXTPNR_PREFIX"

cmake .. \
  -DARCH=ice40 \
  -DICE40_CHIPDB="1k;5k" \
  -DCMAKE_INSTALL_PREFIX="$NEXTPNR_PREFIX" \
  -DICESTORM_INSTALL_PREFIX="$ICESTORM_PREFIX"

# ✅ Fully utilize all CPU cores (no manual RAM control)
make -j"$(nproc)"
make install

# ✅ Fix permissions if mixed user permissions occurred
chown -R "$(id -u):$(id -g)" "$NEXTPNR_PREFIX" "$ICESTORM_PREFIX" || true

info "✅ nextpnr + icestorm installed successfully to $NEXTPNR_PREFIX/bin"
