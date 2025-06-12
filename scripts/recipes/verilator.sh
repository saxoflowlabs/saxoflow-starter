#!/bin/bash

set -e
source "$(dirname "$0")/../common/logger.sh"
source "$(dirname "$0")/../common/paths.sh"
source "$(dirname "$0")/../common/check_deps.sh"
source "$(dirname "$0")/../common/clone_or_update.sh"

info "📦 Installing Verilator from source..."

# --------------------------------------------------
# Step 1 — Dependencies
# --------------------------------------------------
check_deps autoconf g++ flex bison libfl2 libfl-dev \
  zlib1g zlib1g-dev libgoogle-perftools-dev ccache make git

# --------------------------------------------------
# Step 2 — Clone or update repo
# --------------------------------------------------
cd "$TOOLS_DIR"
clone_or_update https://github.com/verilator/verilator verilator

# --------------------------------------------------
# Step 3 — Build and install
# --------------------------------------------------
cd verilator
git checkout stable

# (Only run autoconf if needed)
if [ ! -f configure ]; then
  autoconf
fi

./configure --prefix="$INSTALL_DIR"
make -j"$(nproc)"
make install

info "✅ Verilator installed successfully to $INSTALL_DIR/bin"
