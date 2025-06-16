#!/bin/bash
set -xuo pipefail
set -e

source "$(dirname "$0")/../common/logger.sh"
source "$(dirname "$0")/../common/paths.sh"
source "$(dirname "$0")/../common/check_deps.sh"
source "$(dirname "$0")/../common/clone_or_update.sh"

info "📦 Installing Verilator from source..."

# ✅ Ensure tools dir exists
mkdir -p "$TOOLS_DIR"
cd "$TOOLS_DIR"

# --------------------------------------------------
# Step 1 — Dependencies (added help2man)
# --------------------------------------------------
check_deps autoconf g++ flex bison libfl2 libfl-dev \
  zlib1g zlib1g-dev libgoogle-perftools-dev ccache make git help2man

# --------------------------------------------------
# Step 2 — Clone or update repo
# --------------------------------------------------
clone_or_update https://github.com/verilator/verilator verilator

# --------------------------------------------------
# Step 3 — Build and install cleanly under user path
# --------------------------------------------------
cd verilator
git checkout stable

# Always ensure configure exists
autoconf || true

# ✅ Use fully local prefix
USER_PREFIX="$INSTALL_DIR/verilator"
mkdir -p "$USER_PREFIX"

./configure --prefix="$USER_PREFIX"
make -j"$(nproc)"
make install

# ✅ Sanity: Fix permissions in case earlier runs mixed root
chown -R "$(id -u):$(id -g)" "$USER_PREFIX" || true

# ✅ Final message
info "✅ Verilator installed successfully to $USER_PREFIX/bin"

