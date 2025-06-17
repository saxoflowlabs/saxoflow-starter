# #!/bin/bash

# set -e
# source "$(dirname "$0")/../common/logger.sh"
# source "$(dirname "$0")/../common/paths.sh"
# source "$(dirname "$0")/../common/check_deps.sh"
# source "$(dirname "$0")/../common/clone_or_update.sh"

# info "📦 Installing nextpnr + Project IceStorm..."

# # ✅ Ensure tools dir exists
# mkdir -p "$TOOLS_DIR"
# cd "$TOOLS_DIR"

# # Step 1 — Dependencies
# check_deps \
#   cmake g++ pkg-config libboost-all-dev \
#   libeigen3-dev qtbase5-dev python3-dev libqt5svg5-dev \
#   libftdi-dev libreadline-dev

# # Step 2 — IceStorm Build
# clone_or_update https://github.com/YosysHQ/icestorm.git icestorm

# cd icestorm
# make -j"$(nproc)"
# make install PREFIX="$INSTALL_DIR/icestorm"
# cd "$TOOLS_DIR"

# # Step 3 — nextpnr Build (safe build mode)
# clone_or_update https://github.com/YosysHQ/nextpnr.git nextpnr

# cd nextpnr
# mkdir -p build && cd build

# cmake .. \
#   -DARCH=ice40 \
#   -DICE40_CHIPDB="1k;5k" \
#   -DCMAKE_INSTALL_PREFIX="$INSTALL_DIR/nextpnr" \
#   -DICESTORM_INSTALL_PREFIX="$INSTALL_DIR/icestorm"

# # ✅ Limit parallelism for chipdb stages
# make -j2
# make install

# chown -R "$(id -u):$(id -g)" "$INSTALL_DIR/nextpnr" "$INSTALL_DIR/icestorm" || true

# info "✅ nextpnr + icestorm installed successfully to $INSTALL_DIR/nextpnr/bin"


#!/bin/bash

set -e
set -xuo pipefail

source "$(dirname "$0")/../common/logger.sh"
source "$(dirname "$0")/../common/paths.sh"
source "$(dirname "$0")/../common/check_deps.sh"
source "$(dirname "$0")/../common/clone_or_update.sh"

info "📦 Installing nextpnr + Project IceStorm..."

# ✅ Ensure tools dir exists
mkdir -p "$TOOLS_DIR"
cd "$TOOLS_DIR"

# --------------------------------------------------
# Step 1 — Dependencies
# --------------------------------------------------
check_deps \
  cmake g++ pkg-config libboost-all-dev \
  libeigen3-dev qtbase5-dev python3-dev libqt5svg5-dev \
  libftdi-dev libreadline-dev

# --------------------------------------------------
# Step 2 — IceStorm Build
# --------------------------------------------------
clone_or_update https://github.com/YosysHQ/icestorm.git icestorm

cd icestorm

# ✅ Use fully local prefix
USER_PREFIX="$INSTALL_DIR/icestorm"
mkdir -p "$USER_PREFIX"

make -j"$(nproc)"
make install PREFIX="$USER_PREFIX"
cd "$TOOLS_DIR"

# --------------------------------------------------
# Step 3 — nextpnr Build (safe build mode)
# --------------------------------------------------
clone_or_update https://github.com/YosysHQ/nextpnr.git nextpnr

cd nextpnr
mkdir -p build && cd build

# ✅ Use fully local prefix
USER_PREFIX="$INSTALL_DIR/nextpnr"
mkdir -p "$USER_PREFIX"

cmake .. \
  -DARCH=ice40 \
  -DICE40_CHIPDB="1k;5k" \
  -DCMAKE_INSTALL_PREFIX="$USER_PREFIX" \
  -DICESTORM_INSTALL_PREFIX="$INSTALL_DIR/icestorm"

# ✅ Limit parallelism for chipdb stages
make -j2
make install

# ✅ Fix permissions
chown -R "$(id -u):$(id -g)" "$INSTALL_DIR/nextpnr" "$INSTALL_DIR/icestorm" || true

info "✅ nextpnr + icestorm installed successfully to $USER_PREFIX/bin"
