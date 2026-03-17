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

info "Installing Verible (SystemVerilog linter + formatter)..."

USER_PREFIX="$INSTALL_DIR/verible"
BIN_DIR_MANAGED="$USER_PREFIX/bin"
mkdir -p "$BIN_DIR_MANAGED"

check_deps curl tar

# Detect system architecture
ARCH=$(uname -m)
case "$ARCH" in
  x86_64)
    ARCH_BINARY="amd64"
    ;;
  aarch64)
    ARCH_BINARY="arm64"
    ;;
  *)
    fatal "Unsupported architecture: $ARCH. Verible supports x86_64 and aarch64."
    ;;
esac

OS_NAME=$(uname -s)
case "$OS_NAME" in
  Linux)
    OS_BINARY="linux"
    ;;
  Darwin)
    OS_BINARY="macos"
    ;;
  *)
    fatal "Unsupported OS: $OS_NAME. Verible supports Linux and macOS."
    ;;
esac

info "Detecting latest Verible release for $OS_BINARY-$ARCH_BINARY..."

# Fetch the latest release tag from GitHub API
LATEST_TAG=$(curl -fsSL "https://api.github.com/repos/chipsalliance/verible/releases/latest" \
  | grep '"tag_name"' | head -1 | sed 's/.*"tag_name": *"\([^"]*\)".*/\1/')

if [[ -z "$LATEST_TAG" ]]; then
  fatal "Could not resolve latest Verible release tag. Check network connectivity."
fi

info "Latest Verible release: $LATEST_TAG"

# Build the download URL for the binary distribution
RELEASE_URL="https://github.com/chipsalliance/verible/releases/download/${LATEST_TAG}"
ARCHIVE_NAME="verible-${LATEST_TAG}-${OS_BINARY}-${ARCH_BINARY}.tar.gz"
ARCHIVE_URL="${RELEASE_URL}/${ARCHIVE_NAME}"
ARCHIVE_PATH="$TOOLS_DIR/${ARCHIVE_NAME}"

mkdir -p "$TOOLS_DIR"
info "Downloading Verible from $ARCHIVE_URL..."

if ! curl -fsSL -o "$ARCHIVE_PATH" "$ARCHIVE_URL"; then
  fatal "Failed to download Verible from $ARCHIVE_URL. Check that release exists and network is available."
fi

info "Extracting Verible binaries to $BIN_DIR_MANAGED..."
# Extract to tools dir first, then move binaries to our managed location
EXTRACT_DIR="$TOOLS_DIR/verible-extract"
mkdir -p "$EXTRACT_DIR"
tar -xzf "$ARCHIVE_PATH" -C "$EXTRACT_DIR"

# The archive contains a single directory verible-<version> with bin/ subdir
VERIBLE_EXTRACT=$(find "$EXTRACT_DIR" -maxdepth 1 -type d -name "verible-*" | head -1)
if [[ -z "$VERIBLE_EXTRACT" ]]; then
  # Fallback: archive may extract directly to current dir or have different structure
  VERIBLE_EXTRACT="$EXTRACT_DIR"
fi

# Copy binaries to our managed location
if [[ -d "$VERIBLE_EXTRACT/bin" ]]; then
  cp "$VERIBLE_EXTRACT/bin"/verible-* "$BIN_DIR_MANAGED/" || true
elif [[ -d "$VERIBLE_EXTRACT/verible-$LATEST_TAG/bin" ]]; then
  cp "$VERIBLE_EXTRACT/verible-$LATEST_TAG/bin"/verible-* "$BIN_DIR_MANAGED/" || true
else
  # Last resort: find all verible-* binaries recursively
  find "$EXTRACT_DIR" -name "verible-*" -type f -executable -exec cp {} "$BIN_DIR_MANAGED/" \; || true
fi

# Verify binaries were installed
if [[ ! -f "$BIN_DIR_MANAGED/verible-verilog-lint" ]]; then
  fatal "Installation failed: verible-verilog-lint binary not found. Check release archive structure."
fi

if [[ ! -f "$BIN_DIR_MANAGED/verible-verilog-format" ]]; then
  fatal "Installation failed: verible-verilog-format binary not found. Check release archive structure."
fi

# Make binaries executable (should already be, but ensure)
chmod +x "$BIN_DIR_MANAGED"/verible-*

# Clean up extraction directory
rm -rf "$EXTRACT_DIR"
rm -f "$ARCHIVE_PATH"

persist_path_entry "$BIN_DIR_MANAGED" "Added by SaxoFlow verible installer"

# Verify installation
info "Verifying Verible binaries..."
if "$BIN_DIR_MANAGED/verible-verilog-lint" --version > /dev/null 2>&1; then
  LINT_VERSION=$("$BIN_DIR_MANAGED/verible-verilog-lint" --version 2>&1 | head -1 || echo "v0.0-unknown")
  info "✓ verible-verilog-lint: $LINT_VERSION"
else
  warn "Could not verify verible-verilog-lint version"
fi

if "$BIN_DIR_MANAGED/verible-verilog-format" --version > /dev/null 2>&1; then
  FORMAT_VERSION=$("$BIN_DIR_MANAGED/verible-verilog-format" --version 2>&1 | head -1 || echo "v0.0-unknown")
  info "✓ verible-verilog-format: $FORMAT_VERSION"
else
  warn "Could not verify verible-verilog-format version"
fi

info "Verible installed successfully to $BIN_DIR_MANAGED"
