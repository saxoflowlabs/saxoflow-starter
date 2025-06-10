#!/bin/bash

set -e
source "$(dirname "$0")/check_deps.sh"

INSTALL_DIR="$HOME/.local"
TOOLS_DIR="$(pwd)/tools-src"

echo "📦 Installing OpenROAD from source..."

# Step 1: Install basic dependencies
check_deps \
    build-essential cmake g++ clang bison flex libreadline-dev \
    gawk tcl-dev libffi-dev git graphviz xdot pkg-config \
    python3 python3-pip libboost-all-dev swig libgtest-dev libspdlog-dev \
    libx11-dev libgl1-mesa-dev libxrender-dev libxrandr-dev libxcursor-dev \
    libxi-dev zlib1g-dev doxygen

# Step 2: Build GoogleTest if not already built
if ! ldconfig -p | grep -q libgtest; then
    echo "⚙️ Building and installing GTest..."

    TMPDIR=$(mktemp -d)
    pushd "$TMPDIR"
    cp -r /usr/src/googletest .
    cd googletest
    cmake -S . -B build
    cmake --build build
    sudo cp build/lib/*.a /usr/lib
    popd
    rm -rf "$TMPDIR"
fi

# Step 3: Build LEMON if not already installed
if [ ! -d "$TOOLS_DIR/lemon" ]; then
    echo "📦 Cloning and building LEMON..."
    mkdir -p "$TOOLS_DIR"
    cd "$TOOLS_DIR"

    # Prevent accidental auth prompt
    git config --global credential.helper ""

    # Clone without auth
    git clone https://github.com/dstein64/lemon.git --depth 1
    cd lemon
    mkdir -p build && cd build
    cmake .. -DCMAKE_INSTALL_PREFIX="$INSTALL_DIR"
    make -j"$(nproc)"
    make install
    cd "$TOOLS_DIR"
else
    echo "ℹ️ LEMON already exists, skipping..."
fi


# Step 4: Clone OpenROAD
cd "$TOOLS_DIR"
if [ -d openroad ]; then
    echo "ℹ️ OpenROAD already exists, skipping clone."
else
    git clone --recursive https://github.com/The-OpenROAD-Project/OpenROAD.git openroad
fi

# Step 5: Build OpenROAD
cd openroad
mkdir -p build && cd build
cmake .. -DCMAKE_INSTALL_PREFIX="$INSTALL_DIR" -DLEMON_ROOT="$INSTALL_DIR"
make -j"$(nproc)"
make install

echo "✅ OpenROAD installed to $INSTALL_DIR/bin"
