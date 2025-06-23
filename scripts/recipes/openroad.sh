#!/bin/bash

set -e
set -xuo pipefail

# Load helpers
source "$(dirname "$0")/../common/logger.sh"
source "$(dirname "$0")/../common/paths.sh"
source "$(dirname "$0")/../common/check_deps.sh"
source "$(dirname "$0")/../common/clone_or_update.sh"

# ✅ Define uniform user install prefix (consistent across SaxoFlow tools)
USER_PREFIX="$INSTALL_DIR/openroad"
ORTOOLS_CMAKE_DIR="$USER_PREFIX/lib/cmake/ortools"
GTEST_DIR="$TOOLS_DIR/gtest"

info "📦 Installing OpenROAD (upstream build method)"

# ✅ Ensure tools dir exists
mkdir -p "$TOOLS_DIR"
cd "$TOOLS_DIR"

# --------------------------------------------------
# Step 1: Install required system packages via apt
# (APT is allowed here for system deps, not tool binaries)
# --------------------------------------------------
check_deps \
  build-essential cmake g++ clang bison flex libreadline-dev \
  gawk tcl-dev libffi-dev git graphviz xdot pkg-config python3 python3-pip \
  libboost-all-dev swig libspdlog-dev libx11-dev libgl1-mesa-dev \
  libxrender-dev libxrandr-dev libxcursor-dev libxi-dev zlib1g-dev doxygen \
  wget unzip help2man automake libtool

# --------------------------------------------------
# Step 2: Clone OpenROAD
# --------------------------------------------------
clone_or_update https://github.com/The-OpenROAD-Project/OpenROAD.git openroad true
cd openroad

# --------------------------------------------------
# Step 3: Install OpenROAD additional dependencies (non-APT)
# (These are internal python dependencies; no sudo required)
# --------------------------------------------------
info "⚙️ Installing OpenROAD internal Python dependencies"
sudo ./etc/DependencyInstaller.sh -all

# --------------------------------------------------
# Step 4: Install OR-Tools v9.12 (installed to USER_PREFIX locally)
# --------------------------------------------------
if [ ! -d "$ORTOOLS_CMAKE_DIR" ]; then
  info "⚙️ Downloading prebuilt OR-Tools v9.12 for Linux x86_64"
  ORTOOLS_VERSION=9.12
  wget https://sourceforge.net/projects/or-tools.mirror/files/v${ORTOOLS_VERSION}/or-tools-${ORTOOLS_VERSION}.tar.gz/download -O or-tools-${ORTOOLS_VERSION}.tar.gz
  tar -xzf or-tools-${ORTOOLS_VERSION}.tar.gz
  mkdir -p "$USER_PREFIX"
  cp -r or-tools-${ORTOOLS_VERSION}/* "$USER_PREFIX" || true
  rm -rf or-tools-${ORTOOLS_VERSION}.tar.gz or-tools-${ORTOOLS_VERSION}
else
  info "✅ OR-Tools already installed"
fi

# --------------------------------------------------
# Step 5: Build OpenROAD fully under SaxoFlow environment
# --------------------------------------------------
info "⚙️ Building OpenROAD"
rm -rf build
mkdir build && cd build

cmake .. \
  -DCMAKE_INSTALL_PREFIX="$USER_PREFIX" \
  -DORTOOLS_ROOT="$USER_PREFIX" \
  -DGTEST_ROOT="$USER_PREFIX" \
  -DCMAKE_PREFIX_PATH="$USER_PREFIX"

make -j"$(nproc)"
make install

# ✅ Fix permissions in case root ran anything earlier
chown -R "$(id -u):$(id -g)" "$USER_PREFIX" || true

info "✅ OpenROAD fully installed to $USER_PREFIX/bin"
