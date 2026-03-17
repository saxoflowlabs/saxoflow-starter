#!/bin/bash
#
# yices.sh — Install Yices 2 SMT solver (QF logic + arithmetic)
#
# Yices 2 is an SMT solver specialized for quantifier-free logic, linear arithmetic,
# and bitvector reasoning. Complementary to z3/boolector for formal verification.
#
# References:
#   https://yices.csl.sri.com/
#   https://github.com/SRI-CSL/yices2
#

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}[yices.sh]${NC} Installing Yices 2 SMT solver..."

# Try APT installation first (Ubuntu 20.04+)
if command -v apt-get &> /dev/null; then
    echo -e "${YELLOW}[yices.sh]${NC} Attempting APT installation..."
    if apt-cache search yices2 2>/dev/null | grep -q "^yices2"; then
        echo -e "${YELLOW}[yices.sh]${NC} Yices found in APT. Installing via apt..."
        sudo apt-get update -qq
        sudo apt-get install -y yices2 gperf
        echo -e "${GREEN}[yices.sh]${NC} Yices 2 installed via APT"
        if command -v yices >/dev/null 2>&1; then
            yices --version
        elif command -v yices-smt2 >/dev/null 2>&1; then
            yices-smt2 --version
        fi
        exit 0
    else
        echo -e "${YELLOW}[yices.sh]${NC} Yices not found in default APT repo. Trying SRI PPA..."
        sudo apt-get update -qq
        sudo apt-get install -y software-properties-common
        if sudo add-apt-repository -y ppa:sri-csl/formal-methods >/dev/null 2>&1; then
            sudo apt-get update -qq
            if sudo apt-get install -y yices2 gperf; then
                echo -e "${GREEN}[yices.sh]${NC} Yices 2 installed via SRI PPA"
                if command -v yices >/dev/null 2>&1; then
                    yices --version
                elif command -v yices-smt2 >/dev/null 2>&1; then
                    yices-smt2 --version
                fi
                exit 0
            fi
        fi
        echo -e "${YELLOW}[yices.sh]${NC} Yices install via APT/PPA failed. Building from source..."
    fi
fi

# Fallback: Build from source
INSTALL_PREFIX="$HOME/.local/yices"
BUILD_TEMP="/tmp/yices_build_$$"

mkdir -p "$BUILD_TEMP"
cd "$BUILD_TEMP"

echo -e "${YELLOW}[yices.sh]${NC} Cloning Yices 2 repository..."
git clone https://github.com/SRI-CSL/yices2.git --depth 1 --quiet
cd yices2

# Install build dependencies if needed
echo -e "${YELLOW}[yices.sh]${NC} Installing build dependencies..."
sudo apt-get update -qq
sudo apt-get install -y build-essential autoconf automake libtool gperf libgmp-dev git

echo -e "${YELLOW}[yices.sh]${NC} Running autoconf bootstrap..."
if [ -x "./autoconf.sh" ]; then
    ./autoconf.sh
fi
if [ ! -f "./configure" ]; then
    autoconf
fi

echo -e "${YELLOW}[yices.sh]${NC} Running configure..."
./configure --prefix="$INSTALL_PREFIX" \
    --enable-mcsat \
    CFLAGS="-O3 -march=native" \
    2>&1

echo -e "${YELLOW}[yices.sh]${NC} Building Yices 2 (this may take 5-10 minutes)..."
make -j "$(nproc)"

echo -e "${YELLOW}[yices.sh]${NC} Installing to $INSTALL_PREFIX..."
make install > /dev/null 2>&1

# Ensure bin directory exists
mkdir -p "$INSTALL_PREFIX/bin"

# Some builds install yices-smt2 but not a plain yices shim.
if [ ! -x "$INSTALL_PREFIX/bin/yices" ]; then
    if [ -x "$INSTALL_PREFIX/bin/yices-smt2" ]; then
        ln -sf "$INSTALL_PREFIX/bin/yices-smt2" "$INSTALL_PREFIX/bin/yices"
    elif [ -x "$INSTALL_PREFIX/bin/yices_smt2" ]; then
        ln -sf "$INSTALL_PREFIX/bin/yices_smt2" "$INSTALL_PREFIX/bin/yices"
    fi
fi

echo -e "${GREEN}[yices.sh]${NC} Yices 2 binary installed"

# Append to venv activation if present
if [ -f "$VIRTUAL_ENV/bin/activate" ]; then
    if ! grep -q "yices" "$VIRTUAL_ENV/bin/activate"; then
        echo "export PATH=\"$INSTALL_PREFIX/bin:\$PATH\"" >> "$VIRTUAL_ENV/bin/activate"
        echo -e "${GREEN}[yices.sh]${NC} Added to venv PATH"
    fi
fi

# Cleanup
cd /
rm -rf "$BUILD_TEMP"

echo -e "${GREEN}[yices.sh]${NC} Yices 2 installation complete"
if command -v yices >/dev/null 2>&1; then
    yices --version
elif [ -x "$INSTALL_PREFIX/bin/yices" ]; then
    "$INSTALL_PREFIX/bin/yices" --version
elif command -v yices-smt2 >/dev/null 2>&1; then
    yices-smt2 --version
else
    echo -e "${RED}[yices.sh]${NC} Warning: yices binary not found in PATH"
fi
