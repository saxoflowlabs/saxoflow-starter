#!/bin/bash

set -e
source "$(dirname "$0")/check_deps.sh"

INSTALL_DIR="$HOME/.local"
TOOLS_DIR="$(pwd)/tools-src"
ORTOOLS_CMAKE_DIR="$INSTALL_DIR/lib/cmake/ortools"

echo "📦 Installing OpenROAD from source..."

# Step 1: Install APT dependencies
check_deps \
    build-essential cmake g++ clang bison flex libreadline-dev \
    gawk tcl-dev libffi-dev git graphviz xdot pkg-config \
    python3 python3-pip libboost-all-dev swig libgtest-dev libspdlog-dev \
    libx11-dev libgl1-mesa-dev libxrender-dev libxrandr-dev libxcursor-dev \
    libxi-dev zlib1g-dev doxygen wget unzip

# Step 2: Build GoogleTest if not already installed
if ! ldconfig -p | grep -q libgtest; then
    echo "⚙️ Building and installing GTest..."
    TMPDIR=$(mktemp -d)
    pushd "$TMPDIR"
    if [ -d /usr/src/googletest ]; then
        cp -r /usr/src/googletest . || true
    else
        git clone https://github.com/google/googletest.git
        mv googletest googletest
    fi
    cd googletest
    cmake -S . -B build
    cmake --build build
    sudo cp build/lib/*.a /usr/lib
    popd
    rm -rf "$TMPDIR"
else
    echo "✅ GTest already installed, skipping."
fi

# Step 3: Clone and build LEMON
mkdir -p "$TOOLS_DIR"
cd "$TOOLS_DIR"
if [ -d lemon ]; then
    echo "ℹ️ LEMON already exists, skipping clone."
else
    echo "📦 Cloning and building LEMON..."
    git clone https://github.com/kyouko-taiga/lemon.git
fi
cd lemon
if [ ! -d build ]; then
    mkdir build
fi
cd build
cmake .. -DCMAKE_INSTALL_PREFIX="$INSTALL_DIR"
make -j"$(nproc)"
make install

# Step 4: Clone and build OR-Tools if not installed
mkdir -p "$TOOLS_DIR"
cd "$TOOLS_DIR"
if [ -f "$ORTOOLS_CMAKE_DIR/ortoolsConfig.cmake" ]; then
    echo "✅ OR-Tools already installed, skipping."
else
    if [ -d or-tools ]; then
        echo "ℹ️ OR-Tools directory already exists, skipping clone."
    else
        echo "📦 Cloning OR-Tools..."
        git clone https://github.com/google/or-tools.git or-tools
    fi
    cd or-tools
    cmake -S . -B build \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX="$INSTALL_DIR" \
        -DBUILD_DEPS=ON \
        -DBUILD_PYTHON=OFF \
        -DBUILD_JAVA=OFF \
        -DBUILD_EXAMPLES=OFF \
        -DBUILD_CXX_SAMPLES=OFF \
        -DBUILD_PYTHON_SAMPLES=OFF
    cmake --build build -j"$(nproc)"
    cmake --install build
fi

# Step 5: Clone OpenROAD
cd "$TOOLS_DIR"
if [ -d openroad ]; then
    echo "ℹ️ OpenROAD already exists, skipping clone."
else
    git clone --recursive https://github.com/The-OpenROAD-Project/OpenROAD.git openroad
fi

# Step 6: Build OpenROAD
echo "⚙️ Configuring and building OpenROAD..."
cd "$TOOLS_DIR/openroad"
rm -rf build
mkdir -p build && cd build
cmake .. \
    -DCMAKE_INSTALL_PREFIX="$INSTALL_DIR" \
    -DLEMON_ROOT="$INSTALL_DIR" \
    -Dortools_DIR="$ORTOOLS_CMAKE_DIR"
make -j"$(nproc)"
make install

echo "✅ OpenROAD installed to $INSTALL_DIR/bin"
