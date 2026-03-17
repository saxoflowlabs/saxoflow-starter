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

info "Installing sv2v (SystemVerilog → Verilog converter)..."

USER_PREFIX="$INSTALL_DIR/sv2v"
BIN_DIR_MANAGED="$USER_PREFIX/bin"
mkdir -p "$BIN_DIR_MANAGED"

check_deps curl

# Fetch the latest release tag from GitHub API
info "Resolving latest sv2v release..."
LATEST_TAG=$(curl -fsSL "https://api.github.com/repos/zachjs/sv2v/releases/latest" \
  | grep '"tag_name"' | head -1 | sed 's/.*"tag_name": *"\([^"]*\)".*/\1/')

if [[ -z "$LATEST_TAG" ]]; then
  fatal "Could not resolve latest sv2v release tag. Check network connectivity."
fi

info "Latest sv2v release: $LATEST_TAG"

# Build the download URL for the Linux x86_64 binary
ARCHIVE_URL="https://github.com/zachjs/sv2v/releases/download/${LATEST_TAG}/sv2v-Linux.zip"
ARCHIVE_PATH="$TOOLS_DIR/sv2v-Linux.zip"

mkdir -p "$TOOLS_DIR"
info "Downloading sv2v from $ARCHIVE_URL..."
curl -fsSL -o "$ARCHIVE_PATH" "$ARCHIVE_URL"

# Extract the single binary
EXTRACT_DIR="$TOOLS_DIR/sv2v-extract"
rm -rf "$EXTRACT_DIR"
mkdir -p "$EXTRACT_DIR"

check_deps unzip
unzip -q "$ARCHIVE_PATH" -d "$EXTRACT_DIR"

# The archive contains sv2v binary directly or under a subdirectory
SV2V_BIN=$(find "$EXTRACT_DIR" -type f -name "sv2v" -perm -u+x | head -1)
if [[ -z "$SV2V_BIN" ]]; then
  # Not marked executable — look for any file named sv2v
  SV2V_BIN=$(find "$EXTRACT_DIR" -type f -name "sv2v" | head -1)
fi

if [[ -z "$SV2V_BIN" ]]; then
  fatal "sv2v binary not found in downloaded archive."
fi

cp -f "$SV2V_BIN" "$BIN_DIR_MANAGED/sv2v"
chmod +x "$BIN_DIR_MANAGED/sv2v"

# Cleanup
rm -rf "$ARCHIVE_PATH" "$EXTRACT_DIR"

chown -R "$(id -u):$(id -g)" "$USER_PREFIX" || true

persist_path_entry "$BIN_DIR_MANAGED" "Added by SaxoFlow sv2v installer"

if "$BIN_DIR_MANAGED/sv2v" --version >/dev/null 2>&1; then
  success "sv2v installed successfully to $BIN_DIR_MANAGED"
  info "Detected version: $($BIN_DIR_MANAGED/sv2v --version 2>&1 | head -1)"
else
  fatal "sv2v binary was not found after installation"
fi
