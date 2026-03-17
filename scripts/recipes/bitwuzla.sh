#!/bin/bash
#
# bitwuzla.sh — Install Bitwuzla SMT solver (bitvector-specialized)
#
# Bitwuzla is a high-performance SMT solver optimized for bitvector and array reasoning.
# Useful for formal verification of arithmetic logic and data-path circuits.
#
# References:
#   https://bitwuzla.github.io/
#   https://github.com/bitwuzla/bitwuzla
#

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}[bitwuzla.sh]${NC} Installing Bitwuzla SMT solver..."

# Check if APT package is available (Ubuntu 22.04+)
if command -v apt-get &> /dev/null; then
    echo -e "${YELLOW}[bitwuzla.sh]${NC} Attempting APT installation..."
    if apt-cache search bitwuzla 2>/dev/null | grep -q "^bitwuzla"; then
        echo -e "${YELLOW}[bitwuzla.sh]${NC} Bitwuzla found in APT. Installing via apt..."
        sudo apt-get update -qq
        sudo apt-get install -y bitwuzla
        echo -e "${GREEN}[bitwuzla.sh]${NC} Bitwuzla installed via APT"
        bitwuzla --version
        exit 0
    else
        echo -e "${YELLOW}[bitwuzla.sh]${NC} Bitwuzla not found in APT. Building from source..."
    fi
fi

# Fallback: Build from source
INSTALL_PREFIX="$HOME/.local/bitwuzla"
BUILD_TEMP="/tmp/bitwuzla_build_$$"

echo -e "${YELLOW}[bitwuzla.sh]${NC} Installing build dependencies..."
sudo apt-get update -qq
sudo apt-get install -y \
    build-essential \
    python3 \
    python3-pip \
    meson \
    ninja-build \
    libgmp-dev \
    libmpfr-dev \
    git

mkdir -p "$BUILD_TEMP"
cd "$BUILD_TEMP"

echo -e "${YELLOW}[bitwuzla.sh]${NC} Cloning Bitwuzla repository..."
git clone https://github.com/bitwuzla/bitwuzla.git --depth 1 --quiet
cd bitwuzla

echo -e "${YELLOW}[bitwuzla.sh]${NC} Configuring Bitwuzla (Meson via configure.py)..."
./configure.py --prefix "$INSTALL_PREFIX"

cd build

echo -e "${YELLOW}[bitwuzla.sh]${NC} Building Bitwuzla (this may take 5-10 minutes)..."
ninja

echo -e "${YELLOW}[bitwuzla.sh]${NC} Installing to $INSTALL_PREFIX..."
ninja install

# Add to PATH
mkdir -p "$INSTALL_PREFIX/bin"
if [ -f "$INSTALL_PREFIX/bin/bitwuzla" ]; then
    echo -e "${GREEN}[bitwuzla.sh]${NC} Bitwuzla binary installed"
else
    # Try to find the binary in build directory
    if [ -f "bin/bitwuzla" ]; then
        cp bin/bitwuzla "$INSTALL_PREFIX/bin/" || true
        echo -e "${GREEN}[bitwuzla.sh]${NC} Bitwuzla binary copied to bin/"
    fi
fi

# Append to venv activation if present
if [ -f "$VIRTUAL_ENV/bin/activate" ]; then
    if ! grep -q "bitwuzla" "$VIRTUAL_ENV/bin/activate"; then
        echo "export PATH=\"$INSTALL_PREFIX/bin:\$PATH\"" >> "$VIRTUAL_ENV/bin/activate"
        echo -e "${GREEN}[bitwuzla.sh]${NC} Added to venv PATH"
    fi
fi

# Cleanup
cd /
rm -rf "$BUILD_TEMP"

echo -e "${GREEN}[bitwuzla.sh]${NC} Bitwuzla installation complete"
if command -v bitwuzla >/dev/null 2>&1; then
    bitwuzla --version
elif [ -x "$INSTALL_PREFIX/bin/bitwuzla" ]; then
    "$INSTALL_PREFIX/bin/bitwuzla" --version
else
    echo -e "${RED}[bitwuzla.sh]${NC} Warning: bitwuzla binary not found in expected location"
fi
