#!/bin/bash

set -e
set -xuo pipefail

# Load helpers
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/logger.sh"
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/paths.sh"
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/check_deps.sh"
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/clone_or_update.sh"

# ✅ Define uniform user install prefix (consistent across SaxoFlow tools)
USER_PREFIX="$INSTALL_DIR/openroad"
ORTOOLS_CMAKE_DIR="$USER_PREFIX/lib/cmake/ortools"
GTEST_DIR="$TOOLS_DIR/gtest"

info "Installing OpenROAD (upstream build method)"

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
# Use -base only (installs apt packages). Avoid -all which builds
# Boost and Eigen from source and takes 5+ hours on a single thread.
# absl (abseil-cpp), Eigen, and Boost are installed via apt here.
# --------------------------------------------------
info "Installing OpenROAD base system dependencies"
sudo apt-get install -y \
  libeigen3-dev \
  libboost-all-dev \
  libabsl-dev
sudo ./etc/DependencyInstaller.sh -base

# --------------------------------------------------
# Step 4: Install OR-Tools v9.12 prebuilt (from official GitHub release)
# Bundled absl cmake configs are exposed via CMAKE_PREFIX_PATH in Step 5.
# --------------------------------------------------
if [ ! -d "$ORTOOLS_CMAKE_DIR" ]; then
  info "Downloading prebuilt OR-Tools v9.12 for Linux x86_64"
  # Tag on GitHub releases page is "v9.12"; filenames use the full build "9.12.4544"
  ORTOOLS_TAG="v9.12"
  ORTOOLS_BUILD="9.12.4544"
  # Detect Ubuntu version for the correct prebuilt binary
  UBUNTU_VER=$(lsb_release -rs 2>/dev/null || echo "22.04")
  ORTOOLS_ARCHIVE="or-tools_amd64_ubuntu-${UBUNTU_VER}_cpp_v${ORTOOLS_BUILD}.tar.gz"
  ORTOOLS_URL="https://github.com/google/or-tools/releases/download/${ORTOOLS_TAG}/${ORTOOLS_ARCHIVE}"
  info "Fetching: $ORTOOLS_URL"
  wget --show-progress -O "${ORTOOLS_ARCHIVE}" "${ORTOOLS_URL}" || {
    # Fallback: try Ubuntu 22.04 build if distro-specific one not found
    ORTOOLS_ARCHIVE="or-tools_amd64_ubuntu-22.04_cpp_v${ORTOOLS_BUILD}.tar.gz"
    ORTOOLS_URL="https://github.com/google/or-tools/releases/download/${ORTOOLS_TAG}/${ORTOOLS_ARCHIVE}"
    info "Retrying with fallback: $ORTOOLS_URL"
    wget --show-progress -O "${ORTOOLS_ARCHIVE}" "${ORTOOLS_URL}"
  }
  mkdir -p "$USER_PREFIX"
  tar -xzf "${ORTOOLS_ARCHIVE}" --strip-components=1 -C "$USER_PREFIX"
  rm -f "${ORTOOLS_ARCHIVE}"
else
  info "OR-Tools already installed at $ORTOOLS_CMAKE_DIR"
fi

# --------------------------------------------------
# Step 5: Build OpenROAD fully under SaxoFlow environment
# --------------------------------------------------
info "Building OpenROAD"
rm -rf build
mkdir build && cd build

cmake .. \
  -DCMAKE_INSTALL_PREFIX="$USER_PREFIX" \
  -DORTOOLS_ROOT="$USER_PREFIX" \
  -DGTEST_ROOT="$USER_PREFIX" \
  -DCMAKE_PREFIX_PATH="$USER_PREFIX;/usr" \
  -Dabsl_DIR="$USER_PREFIX/lib/cmake/absl" \
  -DCMAKE_BUILD_TYPE=Release

make -j"$(nproc)"
make install

# ✅ Fix permissions in case root ran anything earlier
chown -R "$(id -u):$(id -g)" "$USER_PREFIX" || true

info "OpenROAD fully installed to $USER_PREFIX/bin"
