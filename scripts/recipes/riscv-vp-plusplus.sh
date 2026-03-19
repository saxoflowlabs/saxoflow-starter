#!/usr/bin/env bash

set -Eeuo pipefail

# shellcheck source=/dev/null
source "$(dirname "$0")/../common/logger.sh"
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/paths.sh"
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/persist_path.sh"
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/check_deps.sh"

info "Installing riscv-vp-plusplus (source build)..."

USER_PREFIX="$INSTALL_DIR/riscv-vp-plusplus"
BIN_DIR_MANAGED="$USER_PREFIX/bin"
VP_REPO="${RISCV_VP_REPO:-https://github.com/agra-uni-bremen/riscv-vp.git}"
VP_REF="${RISCV_VP_REF:-master}"

check_deps git cmake ninja-build g++ make python3 libboost-program-options-dev libboost-log-dev

CMAKE_BIN="cmake"
if [[ -x /usr/bin/cmake ]]; then
  CMAKE_BIN="/usr/bin/cmake"
fi

rm -rf "$USER_PREFIX"
mkdir -p "$USER_PREFIX" "$BIN_DIR_MANAGED"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

SRC_DIR="$TMP_DIR/riscv-vp-src"

git clone --depth 1 --branch "$VP_REF" "$VP_REPO" "$SRC_DIR"
git -C "$SRC_DIR" submodule update --init --recursive

# Build VP directly (skip top-level auxiliary GUI target).
BUILD_DIR="$SRC_DIR/vp/build"
env \
  CMAKE_PREFIX_PATH="/usr;/usr/local" \
  CMAKE_IGNORE_PREFIX_PATH="$HOME/.local" \
  "$CMAKE_BIN" -S "$SRC_DIR/vp" -B "$BUILD_DIR" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DUSE_SYSTEM_SYSTEMC=OFF \
    -DBoost_NO_BOOST_CMAKE=ON \
    -DBOOST_ROOT=/usr \
    -DBoost_INCLUDE_DIR=/usr/include \
    -DBoost_LIBRARY_DIR=/usr/lib/x86_64-linux-gnu
"$CMAKE_BIN" --build "$BUILD_DIR" -- -j"$(nproc)"

VP_BIN=""
for candidate in \
  "$SRC_DIR/vp/build/bin/riscv-vp" \
  "$SRC_DIR/vp/build/src/platform/basic/riscv-vp" \
  "$SRC_DIR/vp/build/bin/riscv-vp-plusplus" \
  "$SRC_DIR/vp/build/src/platform/basic/riscv-vp-plusplus"; do
  if [[ -x "$candidate" ]]; then
    VP_BIN="$candidate"
    break
  fi
done
if [[ -z "$VP_BIN" ]]; then
  VP_BIN="$(find "$SRC_DIR/vp/build" -maxdepth 8 -type f \( -name riscv-vp -o -name riscv-vp-plusplus \) -perm -111 2>/dev/null | head -n1 || true)"
fi

if [[ -z "$VP_BIN" || ! -x "$VP_BIN" ]]; then
  fatal "riscv-vp-plusplus binary was not found after build"
fi

cp "$VP_BIN" "$BIN_DIR_MANAGED/riscv-vp-plusplus"
chmod +x "$BIN_DIR_MANAGED/riscv-vp-plusplus"
ln -sfn "$BIN_DIR_MANAGED/riscv-vp-plusplus" "$BIN_DIR_MANAGED/riscv-vp"

chown -R "$(id -u):$(id -g)" "$USER_PREFIX" || true
persist_path_entry "$BIN_DIR_MANAGED" "Added by SaxoFlow riscv-vp-plusplus installer"

if "$BIN_DIR_MANAGED/riscv-vp-plusplus" --version >/dev/null 2>&1; then
  success "riscv-vp-plusplus installed successfully to $BIN_DIR_MANAGED"
  info "Detected version: $("$BIN_DIR_MANAGED/riscv-vp-plusplus" --version 2>&1 | head -n1)"
else
  warning "riscv-vp-plusplus installed but --version is unsupported; binary is present at $BIN_DIR_MANAGED/riscv-vp-plusplus"
fi
