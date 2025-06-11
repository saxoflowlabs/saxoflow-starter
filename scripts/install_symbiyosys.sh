#!/bin/bash

set -e
source "$(dirname "$0")/check_deps.sh"

INSTALL_DIR="$HOME/.local"
TOOLS_DIR="$(pwd)/tools-src"

echo "📦 Installing SymbiYosys..."

# Install dependencies
check_deps git make python3 python3-pip yosys

# Create tools-src if not exists
mkdir -p "$TOOLS_DIR"
cd "$TOOLS_DIR"

# Clone repo if not already cloned
if [ -d symbiyosys ]; then
    echo "ℹ️ symbiyosys directory already exists, pulling latest changes..."
    cd symbiyosys
    git pull
else
    echo "📦 Cloning SymbiYosys repository..."
    git clone https://github.com/YosysHQ/symbiyosys.git
    cd symbiyosys
fi

# Build and install
make install PREFIX="$INSTALL_DIR"

# Add to PATH only if not already there
PROFILE="$HOME/.bashrc"
if ! grep -q "$INSTALL_DIR/bin" "$PROFILE"; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$PROFILE"
    echo "🔧 PATH updated in $PROFILE"
fi

echo "✅ SymbiYosys installed to $INSTALL_DIR/bin"
