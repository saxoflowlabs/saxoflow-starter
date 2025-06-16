#!/bin/bash

set -e

# Load helpers
source "$(dirname "$0")/../common/logger.sh"
source "$(dirname "$0")/../common/paths.sh"
source "$(dirname "$0")/../common/check_deps.sh"
source "$(dirname "$0")/../common/clone_or_update.sh"

ORTOOLS_CMAKE_DIR="$INSTALL_DIR/lib/cmake/ortools"
GTEST_DIR="$TOOLS_DIR/gtest"

info "📦 Installing OpenROAD optimized for low-RAM systems..."

# Ensure tools dir exists
mkdir -p "$TOOLS_DIR"
cd "$TOOLS_DIR"

# Install system dependencies
check_deps \
  build-essential cmake g++ clang bison flex libreadline-dev \
  gawk tcl-dev libffi-dev git graphviz xdot pkg-config python3 python3-pip \
  libboost-all-dev swig libspdlog-dev libx11-dev libgl1-mesa-dev \
  libxrender-dev libxrandr-dev libxcursor-dev libxi-dev zlib1g-dev doxygen wget unzip

# Build GoogleTest (always local)
info "⚙️ Building GoogleTest (isolated build)"
clone_or_update https://github.com/google/googletest.git gtest
cd gtest
cmake -S . -B build -DCMAKE_INSTALL_PREFIX="$INSTALL_DIR"
cmake --build build -j$(nproc)
cmake --install build
cd "$TOOLS_DIR"

# Build LEMON
clone_or_update https://github.com/The-OpenROAD-Project/lemon.git lemon
cd lemon
mkdir -p build && cd build
cmake .. -DCMAKE_INSTALL_PREFIX="$INSTALL_DIR"
cmake --build . -- -j$(nproc)
make install
cd "$TOOLS_DIR"

# Download prebuilt OR-Tools binary to avoid heavy build
if [ ! -d "$ORTOOLS_CMAKE_DIR" ]; then
  info "⚙️ Downloading prebuilt OR-Tools for Linux x86_64"
  wget https://github.com/google/or-tools/releases/download/v9.8/or-tools_linux_x86_64_v9.8.tar.gz
  tar -xzf or-tools_linux_x86_64_v9.8.tar.gz
  mv or-tools*/linux-x86-64/* "$INSTALL_DIR"
  rm -rf or-tools_linux_x86_64_v9.8.tar.gz or-tools*
else
  info "✅ OR-Tools already installed"
fi

# Build OpenROAD (final stage)
clone_or_update https://github.com/The-OpenROAD-Project/OpenROAD.git openroad true
cd openroad
rm -rf build
mkdir -p build && cd build

cmake .. \
  -DCMAKE_INSTALL_PREFIX="$INSTALL_DIR" \
  -DLEMON_ROOT="$INSTALL_DIR" \
  -DORTOOLS_ROOT="$INSTALL_DIR" \
  -DGTEST_ROOT="$INSTALL_DIR" \
  -DCMAKE_PREFIX_PATH="$INSTALL_DIR"

# Dynamically control number of threads based on free RAM:
TOTAL_RAM_GB=$(free -g | awk '/^Mem:/{print $2}')
if [[ $TOTAL_RAM_GB -le 8 ]]; then
    JOBS=1
elif [[ $TOTAL_RAM_GB -le 16 ]]; then
    JOBS=2
else
    JOBS=$(nproc)
fi

info "🔧 Low-RAM build mode: using $JOBS threads..."
make -j${JOBS}
make install

info "✅ OpenROAD fully installed to $INSTALL_DIR/bin"
