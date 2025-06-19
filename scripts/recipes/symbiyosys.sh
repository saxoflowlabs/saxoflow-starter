#!/bin/bash

set -e
set -xuo pipefail

# Load helpers
source "$(dirname "$0")/../common/logger.sh"
source "$(dirname "$0")/../common/paths.sh"
source "$(dirname "$0")/../common/check_deps.sh"
source "$(dirname "$0")/../common/clone_or_update.sh"

info "📦 Installing SymbiYosys from source..."

# ✅ Ensure tools dir exists (SaxoFlow-controlled workspace)
mkdir -p "$TOOLS_DIR"
cd "$TOOLS_DIR"

# --------------------------------------------------
# Step 1 — Install dependencies (system-level)
# --------------------------------------------------
check_deps git make python3 python3-pip yosys

# --------------------------------------------------
# Step 2 — Clone or update repository
# --------------------------------------------------
clone_or_update https://github.com/YosysHQ/symbiyosys.git symbiyosys

# --------------------------------------------------
# Step 3 — Build and install cleanly under SaxoFlow prefix
# --------------------------------------------------
cd symbiyosys

# ✅ SaxoFlow-controlled install location
USER_PREFIX="$INSTALL_DIR/sby"
mkdir -p "$USER_PREFIX"

make -j"$(nproc)"
make install PREFIX="$USER_PREFIX"

# ✅ Fix permissions in case mixed user permissions occurred
chown -R "$(id -u):$(id -g)" "$USER_PREFIX" || true

info "✅ SymbiYosys installed successfully to $USER_PREFIX/bin"
