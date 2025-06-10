#!/bin/bash

set -e
source "$(dirname "$0")/check_deps.sh"

INSTALL_DIR="$HOME/.local"

check_deps git make python3 python3-pip yosys

# Step 1: Clone if not already present
mkdir -p tools-src && cd tools-src

if [ -d symbiyosys ]; then
    echo "ℹ️  symbiyosys already exists, skipping clone."
else
    git clone https://github.com/YosysHQ/symbiyosys.git
fi

# Step 2: Install
cd symbiyosys
make install PREFIX="$INSTALL_DIR"

# Step 3: Add to PATH
PROFILE="$HOME/.bashrc"
if ! grep -q "$INSTALL_DIR/bin" "$PROFILE"; then
    echo "export PATH=\"$INSTALL_DIR/bin:\$PATH\"" >> "$PROFILE"
    echo "🔧 PATH updated in $PROFILE"
fi

echo "✅ symbiyosys installed to $INSTALL_DIR/bin"
