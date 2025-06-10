#!/bin/bash

set -e
source "$(dirname "$0")/check_deps.sh"

echo "📦 Installing nextpnr and Project IceStorm from source..."

# Step 1: Dependencies
sudo apt install -y cmake g++ pkg-config libboost-all-dev \
    libeigen3-dev qtbase5-dev python3-dev libqt5svg5-dev \
    libftdi-dev libreadline-dev

mkdir -p tools-src && cd tools-src

# Step 2: Install IceStorm
if [ -d icestorm ]; then
    echo "ℹ️  IceStorm already exists, skipping clone."
else
    git clone https://github.com/YosysHQ/icestorm.git
fi

cd icestorm
make -j$(nproc)
make install PREFIX=$HOME/.local
cd ..

# Step 3: Install nextpnr (out-of-tree build)
if [ -d nextpnr ]; then
    echo "ℹ️  nextpnr already exists, skipping clone."
else
    git clone https://github.com/YosysHQ/nextpnr.git
fi

mkdir -p nextpnr/build
cd nextpnr/build
cmake .. -DARCH=ice40 -DCMAKE_INSTALL_PREFIX=$HOME/.local
make -j$(nproc)
make install
cd ../..

# Step 4: Add to PATH
if ! grep -q 'export PATH="$HOME/.local/bin:$PATH"' ~/.bashrc; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    echo "🔧 PATH updated in ~/.bashrc"
fi

echo "✅ nextpnr and IceStorm installed to ~/.local/bin"
