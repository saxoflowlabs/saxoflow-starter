#!/bin/bash

set -euo pipefail

# shellcheck source=/dev/null
source "$(dirname "$0")/../common/logger.sh"
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/paths.sh"
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/check_deps.sh"
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/clone_or_update.sh"

info "Installing nextpnr + Project IceStorm..."

# ✅ Ensure tools dir exists
mkdir -p "$TOOLS_DIR"
cd "$TOOLS_DIR"

# --------------------------------------------------
# Step 1 — Dependencies (system packages only)
# --------------------------------------------------
check_deps \
  cmake g++ pkg-config libboost-all-dev \
  libeigen3-dev qtbase5-dev python3-dev libqt5svg5-dev \
  libftdi-dev libreadline-dev pybind11-dev

# --------------------------------------------------
# Step 2 — Build IceStorm (dependency for nextpnr)
# --------------------------------------------------
clone_or_update https://github.com/YosysHQ/icestorm.git icestorm

cd icestorm

# ✅ SaxoFlow-controlled IceStorm install location
ICESTORM_PREFIX="$INSTALL_DIR/icestorm"
mkdir -p "$ICESTORM_PREFIX"

make -j"$(nproc)"
make install PREFIX="$ICESTORM_PREFIX"
cd "$TOOLS_DIR"

# --------------------------------------------------
# Step 3 — Build nextpnr with IceStorm linked
# --------------------------------------------------
clone_or_update https://github.com/YosysHQ/nextpnr.git nextpnr true

cd nextpnr
mkdir -p build && cd build

# ✅ SaxoFlow-controlled nextpnr install location
NEXTPNR_PREFIX="$INSTALL_DIR/nextpnr"
mkdir -p "$NEXTPNR_PREFIX"

# Use the real system Python3 (not a venv) so cmake finds python3-dev headers.
# Deactivate any active venv for this build only (subshell is not possible with
# set -e, so we unset venv vars directly).
SYSTEM_PYTHON3="$(command -v python3.12 || command -v python3.11 || command -v python3.10 || echo /usr/bin/python3)"
# Prefer /usr/bin/python3 if it exists (always the system interpreter)
[[ -x /usr/bin/python3 ]] && SYSTEM_PYTHON3=/usr/bin/python3

# Strip the active venv from PATH so cmake's FindPython uses the system install
_SAVED_PATH="$PATH"
export PATH="$(echo "$PATH" | tr ':' '\n' | grep -v "${VIRTUAL_ENV:-__none__}" | tr '\n' ':' | sed 's/:$//')"
unset VIRTUAL_ENV PYTHONHOME 2>/dev/null || true

cmake .. \
  -DARCH=ice40 \
  -DICE40_CHIPDB="1k;5k" \
  -DCMAKE_INSTALL_PREFIX="$NEXTPNR_PREFIX" \
  -DICESTORM_INSTALL_PREFIX="$ICESTORM_PREFIX" \
  -DPYTHON_EXECUTABLE="$SYSTEM_PYTHON3"

export PATH="$_SAVED_PATH"

# ✅ Fully utilize all CPU cores (no manual RAM control)
make -j"$(nproc)"
make install

# ✅ Fix permissions if mixed user permissions occurred
chown -R "$(id -u):$(id -g)" "$NEXTPNR_PREFIX" "$ICESTORM_PREFIX" || true

info "nextpnr + icestorm installed successfully to $NEXTPNR_PREFIX/bin"
