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
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/clone_or_update.sh"

info "Installing riscv-pk (Proxy Kernel) from source..."

mkdir -p "$TOOLS_DIR"
cd "$TOOLS_DIR"

check_deps build-essential git autoconf automake libtool device-tree-compiler

# riscv-pk needs the RISC-V ELF toolchain available first.
# Prefer the SaxoFlow-managed install location, then fall back to PATH lookup.
TOOLCHAIN_BIN_DIR="$INSTALL_DIR/riscv-toolchain/bin"
TOOLCHAIN_CC="$TOOLCHAIN_BIN_DIR/riscv64-unknown-elf-gcc"

if [[ -x "$TOOLCHAIN_CC" ]]; then
  export PATH="$TOOLCHAIN_BIN_DIR:$PATH"
  info "Using managed RISC-V toolchain: $TOOLCHAIN_CC"
elif command -v riscv64-unknown-elf-gcc >/dev/null 2>&1; then
  TOOLCHAIN_CC="$(command -v riscv64-unknown-elf-gcc)"
  info "Using RISC-V toolchain from PATH: $TOOLCHAIN_CC"
else
  fatal "riscv64-unknown-elf-gcc not found. Install 'riscv-toolchain' first and retry."
fi

clone_or_update https://github.com/riscv-software-src/riscv-pk.git riscv-pk false

PK_SRC="$TOOLS_DIR/riscv-pk"
USER_PREFIX="$INSTALL_DIR/riscv-pk"
BIN_DIR_MANAGED="$USER_PREFIX/bin"
TRIPLET_BIN_DIR="$USER_PREFIX/riscv64-unknown-elf/bin"

PK_COMMIT="$(git -C "$PK_SRC" rev-parse --short HEAD 2>/dev/null || true)"

rm -rf "$USER_PREFIX"
mkdir -p "$USER_PREFIX"

cd "$PK_SRC"
mkdir -p build
cd build

info "Configuring riscv-pk..."
../configure --prefix="$USER_PREFIX" --host=riscv64-unknown-elf

info "Building riscv-pk (this may take several minutes)..."
make -j"$(nproc)"
make install

chown -R "$(id -u):$(id -g)" "$USER_PREFIX" || true

persist_path_entry "$BIN_DIR_MANAGED" "Added by SaxoFlow riscv-pk installer"

# riscv-pk commonly installs into a target-triplet bin directory (e.g.
# ~/.local/riscv-pk/riscv64-unknown-elf/bin/pk). Normalize to a stable
# ~/.local/riscv-pk/bin/pk path so SaxoFlow and users can rely on one location.
PK_CANDIDATE=""
if [[ -x "$BIN_DIR_MANAGED/pk" ]]; then
  PK_CANDIDATE="$BIN_DIR_MANAGED/pk"
elif [[ -x "$TRIPLET_BIN_DIR/pk" ]]; then
  PK_CANDIDATE="$TRIPLET_BIN_DIR/pk"
else
  PK_CANDIDATE="$(find "$USER_PREFIX" -type f -name pk -perm -111 2>/dev/null | head -n1 || true)"
fi

if [[ -n "$PK_CANDIDATE" && "$PK_CANDIDATE" != "$BIN_DIR_MANAGED/pk" ]]; then
  mkdir -p "$BIN_DIR_MANAGED"
  ln -sfn "$PK_CANDIDATE" "$BIN_DIR_MANAGED/pk"
  info "Created stable pk symlink: $BIN_DIR_MANAGED/pk -> $PK_CANDIDATE"
fi

if [[ -x "$BIN_DIR_MANAGED/pk" ]]; then
  success "riscv-pk installed successfully to $BIN_DIR_MANAGED"
  info "Detected binary: $BIN_DIR_MANAGED/pk"
  if [[ -n "$PK_COMMIT" ]]; then
    printf '%s\n' "$PK_COMMIT" > "$USER_PREFIX/.saxoflow-version"
    info "Detected source commit: $PK_COMMIT"
  fi
else
  fatal "pk binary was not found after installation"
fi
