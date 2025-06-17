#!/bin/bash
set -xuo pipefail
set -e

source "$(dirname "$0")/../common/logger.sh"
source "$(dirname "$0")/../common/paths.sh"
source "$(dirname "$0")/../common/check_deps.sh"
source "$(dirname "$0")/../common/clone_or_update.sh"

info "📦 Installing Yosys and Slang from official sources..."

# ✅ Ensure tools dir exists
mkdir -p "$TOOLS_DIR"
cd "$TOOLS_DIR"

# --------------------------------------------------
# Step 1 — Dependencies (combined for both Yosys & Slang)
# --------------------------------------------------
check_deps cmake g++ flex bison libreadline-dev tcl-dev libffi-dev libboost-all-dev \
  zlib1g zlib1g-dev python3 python3-pip git make

# --------------------------------------------------
# Step 2 — Clone or update Yosys official repo
# --------------------------------------------------
clone_or_update https://github.com/YosysHQ/yosys.git yosys

# --------------------------------------------------
# Step 3 — Build and install Yosys
# --------------------------------------------------
cd yosys

git checkout main

# ✅ Submodule init required for Yosys internal dependencies
git submodule update --init --recursive

USER_PREFIX="$INSTALL_DIR/yosys"
mkdir -p "$USER_PREFIX"

make -j"$(nproc)"
make install PREFIX="$USER_PREFIX"

# --------------------------------------------------
# Step 4 — Clone or update Slang official repo
# --------------------------------------------------
cd "$TOOLS_DIR"
clone_or_update https://github.com/MikePopoloski/slang.git slang

# --------------------------------------------------
# Step 5 — Build and install Slang
# --------------------------------------------------
cd slang

cmake -B build -DCMAKE_INSTALL_PREFIX="$INSTALL_DIR/slang"
cmake --build build -j"$(nproc)"
cmake --install build

# ✅ Sanity: Fix permissions in case earlier runs mixed root
chown -R "$(id -u):$(id -g)" "$INSTALL_DIR/yosys" "$INSTALL_DIR/slang" || true

# ✅ Final message
info "✅ Yosys and Slang installed successfully"
