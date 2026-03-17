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

info "Installing RISC-V GNU Toolchain (pre-built tarball)..."

USER_PREFIX="$INSTALL_DIR/riscv-toolchain"
BIN_DIR_MANAGED="$USER_PREFIX/bin"
RELEASE_API_URL="https://api.github.com/repos/riscv-collab/riscv-gnu-toolchain/releases/latest"

check_deps curl tar xz-utils

mkdir -p "$TOOLS_DIR"

# Resolve latest release from riscv-collab/riscv-gnu-toolchain
info "Resolving latest RISC-V GNU Toolchain release..."
RELEASE_JSON=$(curl -fsSL "$RELEASE_API_URL")

LATEST_TAG=$(printf '%s\n' "$RELEASE_JSON" \
  | grep '"tag_name"' | head -1 \
  | sed 's/.*"tag_name": *"\([^"]*\)".*/\1/')

if [[ -z "$LATEST_TAG" ]]; then
  fatal "Could not resolve latest riscv-gnu-toolchain release tag. Check network connectivity."
fi

info "Latest release: $LATEST_TAG"

# Download the Ubuntu 22.04 x86_64 ELF variant (bare-metal, most useful for embedded RISC-V work).
# Do not guess release asset names; upstream naming changed from nightly .tar.gz
# to versioned .tar.xz assets.
ARCHIVE_NAME=$(printf '%s\n' "$RELEASE_JSON" \
  | grep '"name": "riscv64-elf-ubuntu-22.04-gcc' | head -1 \
  | sed 's/.*"name": *"\([^"]*\)".*/\1/')

if [[ -z "$ARCHIVE_NAME" ]]; then
  fatal "Could not find a riscv64-elf-ubuntu-22.04-gcc asset in release $LATEST_TAG"
fi

DOWNLOAD_URL="https://github.com/riscv-collab/riscv-gnu-toolchain/releases/download/${LATEST_TAG}/${ARCHIVE_NAME}"
ARCHIVE_PATH="$TOOLS_DIR/${ARCHIVE_NAME}"

info "Downloading toolchain from $DOWNLOAD_URL..."
if ! curl -fsSL -o "$ARCHIVE_PATH" "$DOWNLOAD_URL"; then
  # Fall back to a known stable release asset if the latest download fails.
  STABLE_TAG="2024.02.02"
  ARCHIVE_NAME="riscv64-elf-ubuntu-22.04-gcc-nightly-${STABLE_TAG}-nightly.tar.gz"
  DOWNLOAD_URL="https://github.com/riscv-collab/riscv-gnu-toolchain/releases/download/${STABLE_TAG}/${ARCHIVE_NAME}"
  ARCHIVE_PATH="$TOOLS_DIR/${ARCHIVE_NAME}"
  warn "Primary download failed. Falling back to stable release $STABLE_TAG..."
  curl -fsSL -o "$ARCHIVE_PATH" "$DOWNLOAD_URL"
fi

info "Extracting toolchain (this may take a minute)..."
rm -rf "$USER_PREFIX"
mkdir -p "$USER_PREFIX"
tar -xf "$ARCHIVE_PATH" -C "$USER_PREFIX" --strip-components=1

# Cleanup archive
rm -f "$ARCHIVE_PATH"

chown -R "$(id -u):$(id -g)" "$USER_PREFIX" || true

persist_path_entry "$BIN_DIR_MANAGED" "Added by SaxoFlow RISC-V toolchain installer"

# Validate: check the C compiler is present
if "$BIN_DIR_MANAGED/riscv64-unknown-elf-gcc" --version >/dev/null 2>&1; then
  success "RISC-V GNU Toolchain installed successfully to $BIN_DIR_MANAGED"
  info "Detected version: $($BIN_DIR_MANAGED/riscv64-unknown-elf-gcc --version 2>&1 | head -1)"
else
  fatal "riscv64-unknown-elf-gcc binary was not found after installation"
fi
