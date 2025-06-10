#!/bin/bash

set -e
source "$(dirname "$0")/check_deps.sh"

echo "📦 Installing Verilator from source..."

# Install dependencies
sudo apt update
sudo apt install -y git autoconf g++ flex bison \
  libfl2 libfl-dev zlib1g zlib1g-dev \
  libgoogle-perftools-dev ccache make

# Clone or update
if [ ! -d "verilator" ]; then
    git clone https://github.com/verilator/verilator
else
    echo "ℹ️  verilator/ already exists, pulling latest..."
    cd verilator && git pull && cd ..
fi

# Build
cd verilator
git checkout stable
autoconf

# Use HOME install path
./configure --prefix=$HOME/.local
make -j$(nproc)
make install

# Add to PATH if missing
if ! grep -q "$HOME/.local/bin" ~/.bashrc; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
fi

echo "✅ Verilator installed to $HOME/.local/bin"
