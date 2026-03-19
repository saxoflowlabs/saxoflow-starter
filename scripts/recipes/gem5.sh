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

info "Installing gem5 (source build)..."

USER_PREFIX="$INSTALL_DIR/gem5"
BIN_DIR_MANAGED="$USER_PREFIX/bin"
GEM5_VERSION="${GEM5_VERSION:-v25.1.0.0}"

check_deps git python3 python3-pip scons build-essential zlib1g-dev m4 libgoogle-perftools-dev libboost-all-dev pkg-config

rm -rf "$USER_PREFIX"
mkdir -p "$USER_PREFIX" "$BIN_DIR_MANAGED"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

SRC_DIR="$TMP_DIR/gem5-src"

git clone --depth 1 --branch "$GEM5_VERSION" https://github.com/gem5/gem5.git "$SRC_DIR"

# Build optimized binary for x86 host.
(
  cd "$SRC_DIR"
  # Skip interactive style/hook checks in non-interactive installer runs.
  scons --ignore-style build/X86/gem5.opt -j"$(nproc)"
)

if [[ ! -x "$SRC_DIR/build/X86/gem5.opt" ]]; then
  fatal "gem5 build did not produce build/X86/gem5.opt"
fi

cp "$SRC_DIR/build/X86/gem5.opt" "$BIN_DIR_MANAGED/gem5"
chmod +x "$BIN_DIR_MANAGED/gem5"

chown -R "$(id -u):$(id -g)" "$USER_PREFIX" || true
persist_path_entry "$BIN_DIR_MANAGED" "Added by SaxoFlow gem5 installer"

if "$BIN_DIR_MANAGED/gem5" --help >/dev/null 2>&1; then
  success "gem5 installed successfully to $BIN_DIR_MANAGED"
  GEM5_DETECTED_VERSION="$($BIN_DIR_MANAGED/gem5 --build-info 2>/dev/null | awk '/gem5 version/{print $3; exit}')"
  if [[ -n "$GEM5_DETECTED_VERSION" ]]; then
    info "Detected version: $GEM5_DETECTED_VERSION"
  else
    info "Detected version: version probe unsupported by upstream binary"
  fi
else
  fatal "gem5 binary was not executable after installation"
fi
