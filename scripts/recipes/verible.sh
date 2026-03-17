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

check_deps curl tar python3

# Detect system architecture
ARCH=$(uname -m)
case "$ARCH" in
  x86_64)
    ARCH_BINARY="x86_64"
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
    OS_BINARY="linux-static"
    ;;
  Darwin)
    # Upstream asset names currently use "macOS" in release archives.
    OS_BINARY="macOS"
    ;;
  *)
    fatal "Unsupported OS: $OS_NAME. Verible supports Linux and macOS."
    ;;
esac

info "Detecting latest Verible release for $OS_BINARY-$ARCH_BINARY..."

# Fetch latest release metadata from GitHub API.
LATEST_RELEASE_JSON="$TOOLS_DIR/verible-latest-release.json"
mkdir -p "$TOOLS_DIR"

if ! curl -fsSL -o "$LATEST_RELEASE_JSON" "https://api.github.com/repos/chipsalliance/verible/releases/latest"; then
  fatal "Could not fetch latest Verible release metadata. Check network connectivity."
fi

# Extract release tag.
LATEST_TAG=$(python3 - "$LATEST_RELEASE_JSON" << 'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as f:
    data = json.load(f)

print(data.get("tag_name", ""))
PY
)

if [[ -z "$LATEST_TAG" ]]; then
  fatal "Could not resolve latest Verible release tag. Check network connectivity."
fi

info "Latest Verible release: $LATEST_TAG"

# Resolve matching asset URL from release assets rather than guessing the archive name.
ASSET_URL=$(python3 - "$LATEST_RELEASE_JSON" "$OS_BINARY" "$ARCH_BINARY" << 'PY'
import json
import sys

release_json, os_name, arch_name = sys.argv[1], sys.argv[2], sys.argv[3]

with open(release_json, "r", encoding="utf-8") as f:
    data = json.load(f)

assets = data.get("assets", [])

def pick_url(predicate):
    for a in assets:
        name = a.get("name", "")
        if predicate(name):
            return a.get("browser_download_url", "")
    return ""

# Preferred: exact OS + arch match (Linux and any arch-specific macOS assets).
url = pick_url(lambda n: os_name in n and arch_name in n and n.endswith(".tar.gz"))

# Fallback for macOS assets that don't encode architecture in file name.
if not url and os_name == "macOS":
    url = pick_url(lambda n: "macOS" in n and n.endswith(".tar.gz"))

print(url)
PY
)

if [[ -z "$ASSET_URL" ]]; then
  fatal "Could not locate a compatible Verible release asset for $OS_BINARY-$ARCH_BINARY."
fi

ARCHIVE_NAME="$(basename "$ASSET_URL")"
ARCHIVE_PATH="$TOOLS_DIR/${ARCHIVE_NAME}"

info "Downloading Verible from $ASSET_URL..."

if ! curl -fsSL -o "$ARCHIVE_PATH" "$ASSET_URL"; then
  fatal "Failed to download Verible from $ASSET_URL. Check that release exists and network is available."
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
rm -f "$LATEST_RELEASE_JSON"

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
