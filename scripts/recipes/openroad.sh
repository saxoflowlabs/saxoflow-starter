# #!/bin/bash

# set -e

# # Load helpers
# source "$(dirname "$0")/../common/logger.sh"
# source "$(dirname "$0")/../common/paths.sh"
# source "$(dirname "$0")/../common/check_deps.sh"
# source "$(dirname "$0")/../common/clone_or_update.sh"

# ORTOOLS_CMAKE_DIR="$INSTALL_DIR/lib/cmake/ortools"
# GTEST_DIR="$TOOLS_DIR/gtest"

# info "📦 Installing OpenROAD (upstream build method)"

# # Ensure tools dir exists
# mkdir -p "$TOOLS_DIR"
# cd "$TOOLS_DIR"

# # Step 1: Install required system packages
# check_deps \
#   build-essential cmake g++ clang bison flex libreadline-dev \
#   gawk tcl-dev libffi-dev git graphviz xdot pkg-config python3 python3-pip \
#   libboost-all-dev swig libspdlog-dev libx11-dev libgl1-mesa-dev \
#   libxrender-dev libxrandr-dev libxcursor-dev libxi-dev zlib1g-dev doxygen \
#   wget unzip help2man automake libtool

# # Step 2: Clone OpenROAD
# clone_or_update https://github.com/The-OpenROAD-Project/OpenROAD.git openroad true
# cd openroad








# # Step 4: Install dependencies
# info "⚙️ Installing system dependencies (requires sudo)"
# sudo ./etc/DependencyInstaller.sh -all


# # Step 5: Install OR-Tools v9.12
# if [ ! -d "$ORTOOLS_CMAKE_DIR" ]; then
#   info "⚙️ Downloading prebuilt OR-Tools v9.12 for Linux x86_64"
#   ORTOOLS_VERSION=9.12
#   wget https://sourceforge.net/projects/or-tools.mirror/files/v${ORTOOLS_VERSION}/or-tools-${ORTOOLS_VERSION}.tar.gz/download -O or-tools-${ORTOOLS_VERSION}.tar.gz
#   tar -xzf or-tools-${ORTOOLS_VERSION}.tar.gz
#   mkdir -p "$INSTALL_DIR"
#   cp -r or-tools-${ORTOOLS_VERSION}/* "$INSTALL_DIR" || true
#   rm -rf or-tools-${ORTOOLS_VERSION}.tar.gz or-tools-${ORTOOLS_VERSION}
# else
#   info "✅ OR-Tools already installed"
# fi

# # Step 6: Build OpenROAD
# info "⚙️ Building OpenROAD"
# rm -rf build
# mkdir build && cd build

# cmake .. \
#   -DCMAKE_INSTALL_PREFIX="$INSTALL_DIR" \
#   -DORTOOLS_ROOT="$INSTALL_DIR" \
#   -DGTEST_ROOT="$INSTALL_DIR" \
#   -DCMAKE_PREFIX_PATH="$INSTALL_DIR"

# # RAM-aware parallel build
# TOTAL_RAM_GB=$(free -g | awk '/^Mem:/{print $2}')
# if [[ $TOTAL_RAM_GB -le 8 ]]; then
#     JOBS=1
# elif [[ $TOTAL_RAM_GB -le 16 ]]; then
#     JOBS=2
# else
#     JOBS=$(nproc)
# fi

# info "🔧 Low-RAM build mode: using $JOBS threads..."
# make -j${JOBS}
# make install

# info "✅ OpenROAD fully installed to $INSTALL_DIR/bin"


#!/bin/bash

#!/bin/bash

set -e
set -xuo pipefail

# Load helpers
source "$(dirname "$0")/../common/logger.sh"
source "$(dirname "$0")/../common/paths.sh"
source "$(dirname "$0")/../common/check_deps.sh"
source "$(dirname "$0")/../common/clone_or_update.sh"

# ✅ Define uniform user install prefix (consistent across tools)
USER_PREFIX="$INSTALL_DIR/openroad"
ORTOOLS_CMAKE_DIR="$USER_PREFIX/lib/cmake/ortools"
GTEST_DIR="$TOOLS_DIR/gtest"

info "📦 Installing OpenROAD (upstream build method)"

# Ensure tools dir exists
mkdir -p "$TOOLS_DIR"
cd "$TOOLS_DIR"

# Step 1: Install required system packages
check_deps \
  build-essential cmake g++ clang bison flex libreadline-dev \
  gawk tcl-dev libffi-dev git graphviz xdot pkg-config python3 python3-pip \
  libboost-all-dev swig libspdlog-dev libx11-dev libgl1-mesa-dev \
  libxrender-dev libxrandr-dev libxcursor-dev libxi-dev zlib1g-dev doxygen \
  wget unzip help2man automake libtool

# Step 2: Clone OpenROAD
clone_or_update https://github.com/The-OpenROAD-Project/OpenROAD.git openroad true
cd openroad

# Step 3: Install dependencies
info "⚙️ Installing system dependencies (requires sudo)"
sudo ./etc/DependencyInstaller.sh -all

# Step 4: Install OR-Tools v9.12 (to USER_PREFIX, not system-wide!)
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

# Step 5: Build OpenROAD
info "⚙️ Building OpenROAD"
rm -rf build
mkdir build && cd build

cmake .. \
  -DCMAKE_INSTALL_PREFIX="$USER_PREFIX" \
  -DORTOOLS_ROOT="$USER_PREFIX" \
  -DGTEST_ROOT="$USER_PREFIX" \
  -DCMAKE_PREFIX_PATH="$USER_PREFIX"

# ✅ Direct full-parallel build
make -j"$(nproc)"
make install

# ✅ Fix permissions if sudo was involved
chown -R "$(id -u):$(id -g)" "$USER_PREFIX" || true

info "✅ OpenROAD fully installed to $USER_PREFIX/bin"
