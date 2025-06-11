#!/bin/bash

set -e
source "$(dirname "$0")/check_deps.sh"

INSTALL_DIR="$HOME/.local"
TOOLS_DIR="$(pwd)/tools-src"
VERILATOR_DIR="$TOOLS_DIR/verilator"

echo "📦 Installing Verilator from source..."

# Step 1: Install APT dependencies
check_deps \
    git autoconf g++ flex bison \
    libfl2 libfl-dev zlib1g zlib1g-dev \
    libgoogle-perftools-dev ccache make help2man

# Step 2: Prepare source directory
mkdir -p "$TOOLS_DIR"
cd "$TOOLS_DIR"

# Step 3: Clone or update Verilator
if [ -d verilator ]; then
    echo "ℹ️ Verilator repo already exists, updating..."
    cd verilator
    git pull
else
    echo "📦 Cloning Verilator..."
    git clone https://github.com/verilator/verilator.git
    cd verilator
fi

# Step 4: Checkout stable branch
git checkout stable
autoconf

# Step 5: Build Verilator
./configure --prefix="$INSTALL_DIR"
make -j"$(nproc)"
make install

# Step 6: Ensure ~/.local/bin is in PATH
PROFILE_SCRIPT="$HOME/.bashrc"
if ! grep -q 'export PATH="$HOME/.local/bin:$PATH"' "$PROFILE_SCRIPT"; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$PROFILE_SCRIPT"
    echo "🔧 PATH updated in $PROFILE_SCRIPT"
fi

echo "✅ Verilator installed to $INSTALL_DIR/bin"
