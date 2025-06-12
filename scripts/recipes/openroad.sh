#!/bin/bash

set -e
source "$(dirname "$0")/../common/logger.sh"
source "$(dirname "$0")/../common/paths.sh"
source "$(dirname "$0")/../common/check_deps.sh"
source "$(dirname "$0")/../common/clone_or_update.sh"

ORTOOLS_CMAKE_DIR="$INSTALL_DIR/lib/cmake/ortools"

info "📦 Installing OpenROAD complete dependency stack..."

# --------------------------
# STEP 1 — Install core dependencies
# --------------------------
check_deps \
  build-essential cmake g++ clang bison flex libreadline-dev \
  gawk tcl-dev libffi-dev git graphviz xdot pkg-config python3 python3-pip \
  libboost-all-dev swig libgtest-dev libspdlog-dev libx11-dev libgl1-mesa-dev \
  libxrender-dev libxrandr-dev libxcursor-dev libxi-dev zlib1g-dev doxygen wget unzip

# --------------------------
# STEP 2 — Build GoogleTest (only if missing)
# --------------------------
if ! ldconfig -p | grep -q libgtest; then
  info "⚙️ Building GoogleTest..."
  TMPDIR=$(mktemp -d)
  pushd "$TMPDIR"
  cp -r /usr/src/googletest . || true
  cd googletest
  cmake -S . -B build
  cmake --build build
  sudo cp build/lib/*.a /usr/lib
  popd
  rm -rf "$TMPDIR"
else
  info "✅ GoogleTest already installed"
fi

# --------------------------
# STEP 3 — Build LEMON (with idempotency)
# --------------------------
cd "$TOOLS_DIR"
clone_or_update https://github.com/kyouko-taiga/lemon.git lemon

cd lemon
mkdir -p build && cd build
cmake .. -DCMAKE_INSTALL_PREFIX="$INSTALL_DIR"
make -j"$(nproc)"
make install

# --------------------------
# STEP 4 — Build OR-Tools (only if not installed)
# --------------------------
if [ ! -f "$ORTOOLS_CMAKE_DIR/ortoolsConfig.cmake" ]; then
  info "⚙️ Building OR-Tools..."
  cd "$TOOLS_DIR"
  clone_or_update https://github.com/google/or-tools.git or-tools

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
else
  info "✅ OR-Tools already installed"
fi

# --------------------------
# STEP 5 — Build OpenROAD
# --------------------------
cd "$TOOLS_DIR"
clone_or_update --recursive https://github.com/The-OpenROAD-Project/OpenROAD.git openroad

cd openroad

# Fully clean build always for OpenROAD
rm -rf build
mkdir -p build && cd build

cmake .. \
  -DCMAKE_INSTALL_PREFIX="$INSTALL_DIR" \
  -DLEMON_ROOT="$INSTALL_DIR" \
  -Dortools_DIR="$ORTOOLS_CMAKE_DIR"

make -j"$(nproc)"
make install

info "✅ OpenROAD fully installed at $INSTALL_DIR/bin"
