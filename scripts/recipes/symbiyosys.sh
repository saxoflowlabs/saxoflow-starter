#!/bin/bash

set -e
source "$(dirname "$0")/../common/logger.sh"
source "$(dirname "$0")/../common/paths.sh"
source "$(dirname "$0")/../common/check_deps.sh"
source "$(dirname "$0")/../common/clone_or_update.sh"

info "📦 Installing SymbiYosys from source..."

# ✅ PRO PATCH: Ensure tools dir exists
mkdir -p "$TOOLS_DIR"
cd "$TOOLS_DIR"

# --------------------------------------------------
# Step 1 — Install dependencies
# --------------------------------------------------
check_deps git make python3 python3-pip yosys

# --------------------------------------------------
# Step 2 — Clone or update repository
# --------------------------------------------------
clone_or_update https://github.com/YosysHQ/symbiyosys.git symbiyosys

# --------------------------------------------------
# Step 3 — Build and install
# --------------------------------------------------
cd symbiyosys
make -j"$(nproc)"
make install PREFIX="$INSTALL_DIR"

info "✅ SymbiYosys installed successfully to $INSTALL_DIR/bin"
