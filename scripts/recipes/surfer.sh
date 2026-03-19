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

info "Installing Surfer waveform viewer..."

USER_PREFIX="$INSTALL_DIR/surfer"
BIN_DIR_MANAGED="$USER_PREFIX/bin"

# Build requirements for Rust crates and TLS-enabled fetches.
check_deps curl build-essential pkg-config libssl-dev

# Ensure a Rust toolchain is available for cargo-based install.
if ! command -v cargo >/dev/null 2>&1; then
  info "cargo not found. Bootstrapping Rust toolchain via rustup..."
  if ! command -v rustup >/dev/null 2>&1; then
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
  fi
  export PATH="$HOME/.cargo/bin:$PATH"
fi

if ! command -v cargo >/dev/null 2>&1; then
  fatal "cargo is required to install surfer but was not found after rustup bootstrap"
fi

rm -rf "$USER_PREFIX"
mkdir -p "$USER_PREFIX"

# Install pinned crate artifacts under a SaxoFlow-managed prefix.
cargo install --locked --root "$USER_PREFIX" surfer

chown -R "$(id -u):$(id -g)" "$USER_PREFIX" || true

persist_path_entry "$BIN_DIR_MANAGED" "Added by SaxoFlow Surfer installer"

# Some surfer crate releases expose a differently named executable
# (e.g. `test_main`). Normalize to a stable `surfer` command.
SURFER_CANDIDATE=""
for name in surfer test_main; do
  if [[ -x "$BIN_DIR_MANAGED/$name" ]]; then
    SURFER_CANDIDATE="$BIN_DIR_MANAGED/$name"
    break
  fi
done

if [[ -z "$SURFER_CANDIDATE" ]]; then
  SURFER_CANDIDATE="$(find "$BIN_DIR_MANAGED" -maxdepth 1 -type f -perm -111 2>/dev/null | head -n1 || true)"
fi

if [[ -n "$SURFER_CANDIDATE" && "$SURFER_CANDIDATE" != "$BIN_DIR_MANAGED/surfer" ]]; then
  ln -sfn "$SURFER_CANDIDATE" "$BIN_DIR_MANAGED/surfer"
  info "Created stable surfer symlink: $BIN_DIR_MANAGED/surfer -> $SURFER_CANDIDATE"
fi

if [[ -x "$BIN_DIR_MANAGED/surfer" ]]; then
  success "Surfer installed successfully to $BIN_DIR_MANAGED"
  VERSION_LINE="$(timeout 5s "$BIN_DIR_MANAGED/surfer" --version 2>&1 | head -n1 || true)"
  if [[ -n "$VERSION_LINE" ]]; then
    info "Detected version: $VERSION_LINE"
  else
    info "Detected version: (version probe unsupported by upstream binary)"
  fi
else
  fatal "surfer binary was not found after installation"
fi
