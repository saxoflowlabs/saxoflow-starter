#!/bin/bash
set -e

echo "📦 Installing nextpnr from source..."

# Install dependencies
sudo apt install -y cmake g++ pkg-config libboost-all-dev \
    libeigen3-dev qtbase5-dev python3-dev libqt5svg5-dev

# Clone and build nextpnr (generic arch by default)
git clone https://github.com/YosysHQ/nextpnr.git
cd nextpnr
cmake -DARCH=generic -DCMAKE_INSTALL_PREFIX=$HOME/.local .
make -j$(nproc)
make install

# Add to PATH
if ! grep -q '$HOME/.local/bin' ~/.bashrc; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
fi

echo "✅ nextpnr installed to ~/.local/bin"
