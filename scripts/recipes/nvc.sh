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

info "Installing NVC VHDL compiler/simulator..."

USER_PREFIX="$INSTALL_DIR/nvc"
BIN_DIR_MANAGED="$USER_PREFIX/bin"
NVC_RELEASE_TAG="${NVC_RELEASE_TAG:-r1.19.3}"

check_deps curl dpkg

if ! command -v dpkg-deb >/dev/null 2>&1; then
  fatal "dpkg-deb command is required but not available (install package: dpkg)"
fi

rm -rf "$USER_PREFIX"
mkdir -p "$USER_PREFIX" "$BIN_DIR_MANAGED"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

# Select upstream .deb asset by distro version. We prefer Ubuntu-matched builds
# because apt package `nvc` is not consistently available across Debian-based hosts.
ASSET_NAME=""
if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  source /etc/os-release
  if [[ "${ID:-}" == "ubuntu" && "${VERSION_ID:-}" == "24.04" ]]; then
    ASSET_NAME="nvc_1.19.3-1_amd64_ubuntu-24.04.deb"
  elif [[ "${ID:-}" == "ubuntu" && "${VERSION_ID:-}" == "22.04" ]]; then
    ASSET_NAME="nvc_1.19.3-1_amd64_ubuntu-22.04.deb"
  fi
fi

# Conservative fallback for other Linux environments.
if [[ -z "$ASSET_NAME" ]]; then
  ASSET_NAME="nvc_1.19.3-1_amd64_ubuntu-22.04.deb"
  info "Using fallback NVC artifact: $ASSET_NAME"
fi

DEB_URL="https://github.com/nickg/nvc/releases/download/${NVC_RELEASE_TAG}/${ASSET_NAME}"
DEB_PATH="$TMP_DIR/nvc.deb"

info "Downloading: $DEB_URL"
curl -fL "$DEB_URL" -o "$DEB_PATH"

dpkg-deb -x "$DEB_PATH" "$USER_PREFIX"

# Normalize binary location into a stable managed bin path.
NVC_CANDIDATE="$USER_PREFIX/usr/bin/nvc"
if [[ ! -x "$NVC_CANDIDATE" ]]; then
  NVC_CANDIDATE="$(find "$USER_PREFIX" -type f -name nvc -perm -111 2>/dev/null | head -n1 || true)"
fi

if [[ -z "$NVC_CANDIDATE" || ! -x "$NVC_CANDIDATE" ]]; then
  fatal "nvc binary was not found after extracting release package"
fi

ln -sfn "$NVC_CANDIDATE" "$BIN_DIR_MANAGED/nvc"

chown -R "$(id -u):$(id -g)" "$USER_PREFIX" || true
persist_path_entry "$BIN_DIR_MANAGED" "Added by SaxoFlow NVC installer"

if "$BIN_DIR_MANAGED/nvc" --version >/dev/null 2>&1; then
  success "NVC installed successfully to $BIN_DIR_MANAGED"
  info "Detected version: $("$BIN_DIR_MANAGED/nvc" --version 2>&1 | head -n1)"
else
  fatal "nvc binary was not executable after installation"
fi
