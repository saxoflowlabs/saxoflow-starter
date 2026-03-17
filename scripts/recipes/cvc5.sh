#!/bin/bash
#
# cvc5.sh — Install CVC5 SMT solver (quantifiers + theory combinations)
#
# CVC5 is a modern SMT solver with strong support for quantified formulas
# and theory combinations. Useful for complex formal properties with
# quantifiers and mixed theories.
#
# References:
#   https://cvc5.github.io/
#   https://github.com/cvc5/cvc5
#

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}[cvc5.sh]${NC} Installing CVC5 SMT solver..."

# Try APT installation first (some newer Ubuntu versions may have it)
if command -v apt-get &> /dev/null; then
    echo -e "${YELLOW}[cvc5.sh]${NC} Checking for CVC5 in APT..."
    if apt-cache search cvc5 2>/dev/null | grep -q "^cvc5"; then
        echo -e "${YELLOW}[cvc5.sh]${NC} CVC5 found in APT. Installing via apt..."
        sudo apt-get update -qq
        sudo apt-get install -y cvc5
        echo -e "${GREEN}[cvc5.sh]${NC} CVC5 installed via APT"
        cvc5 --version
        exit 0
    else
        echo -e "${YELLOW}[cvc5.sh]${NC} CVC5 not in APT. Building from source..."
    fi
fi

# Build from source
INSTALL_PREFIX="$HOME/.local/cvc5"
BUILD_TEMP="/tmp/cvc5_build_$$"

mkdir -p "$BUILD_TEMP"
cd "$BUILD_TEMP"

echo -e "${YELLOW}[cvc5.sh]${NC} Cloning CVC5 repository..."
git clone https://github.com/cvc5/cvc5.git --depth 1 --quiet
cd cvc5

echo -e "${YELLOW}[cvc5.sh]${NC} Installing build dependencies..."
# Check if package lists are already updated
if [ ! -f /var/lib/apt/periodic/update-success-stamp ] || \
   [ "$(find /var/lib/apt/periodic/update-success-stamp -mmin -60 2>/dev/null)" = "" ]; then
    sudo apt-get update -qq
fi

# Install required build tools
BUILD_DEPS="build-essential cmake git python3"
for dep in $BUILD_DEPS; do
    if ! dpkg -l | grep -q "^ii.*$dep"; then
        echo -e "${YELLOW}[cvc5.sh]${NC} Installing $dep..."
        sudo apt-get install -y "$dep" 2>&1 | grep -v "^Setting up" || true
    fi
done

echo -e "${YELLOW}[cvc5.sh]${NC} Running cmake configuration..."
python3 ./configure.py \
    --prefix "$INSTALL_PREFIX" \
    --optimize \
    --static \
    --no-gpl \
    2>&1 | tail -5

echo -e "${YELLOW}[cvc5.sh]${NC} Building CVC5 (this may take 10-20 minutes)..."
cd build
make -j "$(nproc)" 2>&1 | tail -10

echo -e "${YELLOW}[cvc5.sh]${NC} Installing to $INSTALL_PREFIX..."
make install > /dev/null 2>&1

mkdir -p "$INSTALL_PREFIX/bin"
echo -e "${GREEN}[cvc5.sh]${NC} CVC5 binary installed"

# Append to venv activation if present
if [ -f "$VIRTUAL_ENV/bin/activate" ]; then
    if ! grep -q "cvc5" "$VIRTUAL_ENV/bin/activate"; then
        echo "export PATH=\"$INSTALL_PREFIX/bin:\$PATH\"" >> "$VIRTUAL_ENV/bin/activate"
        echo -e "${GREEN}[cvc5.sh]${NC} Added to venv PATH"
    fi
fi

# Cleanup
cd /
rm -rf "$BUILD_TEMP"

echo -e "${GREEN}[cvc5.sh]${NC} CVC5 installation complete"
cvc5 --version > /dev/null 2>&1 || echo -e "${RED}[cvc5.sh]${NC} Warning: cvc5 binary not found in PATH"
