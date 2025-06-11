#!/bin/bash

set -e
source "$(dirname "$0")/check_deps.sh"

INSTALL_DIR="$HOME/.local"
TOOLS_DIR="$(pwd)/tools-src"

echo "📦 Installing nextpnr and Project IceStorm from source..."

# Install dependencies
check_deps cmake g++ pkg-config libboost-all-dev \
    libeigen3-dev qtbase5-dev python3-dev libqt5svg5-dev \
    libftdi-dev libreadline-dev

# Prepare tools-src
mkdir -p "$TOOLS_DIR"
cd "$TOOLS_DIR"

# Build IceStorm
if [ -d icestorm ]; then
    echo "ℹ️ IceStorm directory exists, pulling latest..."
    cd icestorm
    git pull
else
    echo "📦 Cloning IceStorm..."
    git clone https://github.com/YosysHQ/icestorm.git
    cd icestorm
fi

make -j"$(nproc)"
make install PREFIX="$INSTALL_DIR"
cd "$TOOLS_DIR"

# Build nextpnr
if [ -d nextpnr ]; then
    echo "ℹ️ nextpnr directory exists, pulling latest..."
    cd nextpnr
    git pull
else
    echo "📦 Cloning nextpnr..."
    git clone https://github.com/YosysHQ/nextpnr.git
    cd nextpnr
fi

mkdir -p build && cd build
cmake .. -DARCH=ice40 -DCMAKE_INSTALL_PREFIX="$INSTALL_DIR"
make -j"$(nproc)"
make install

# Ensure PATH
PROFILE="$HOME/.bashrc"
if ! grep -q "$INSTALL_DIR/bin" "$PROFILE"; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$PROFILE"
    echo "🔧 PATH updated in $PROFILE"
fi

echo "✅ nextpnr and IceStorm installed to $INSTALL_DIR/bin"
