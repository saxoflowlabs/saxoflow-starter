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

info "Installing Renode (portable Linux package)..."

USER_PREFIX="$INSTALL_DIR/renode"
BIN_DIR_MANAGED="$USER_PREFIX/bin"
RENODE_VERSION="${RENODE_VERSION:-1.16.1}"

check_deps curl tar

rm -rf "$USER_PREFIX"
mkdir -p "$USER_PREFIX" "$BIN_DIR_MANAGED"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

ASSET_NAME="renode-${RENODE_VERSION}.linux-portable.tar.gz"
ASSET_URL="https://github.com/renode/renode/releases/download/v${RENODE_VERSION}/${ASSET_NAME}"
ARCHIVE_PATH="$TMP_DIR/$ASSET_NAME"

info "Downloading: $ASSET_URL"
curl -fL "$ASSET_URL" -o "$ARCHIVE_PATH"

tar -xzf "$ARCHIVE_PATH" -C "$USER_PREFIX" --strip-components=1

RENODE_CANDIDATE=""
for p in "$USER_PREFIX/renode" "$USER_PREFIX/Renode"; do
  if [[ -x "$p" ]]; then
    RENODE_CANDIDATE="$p"
    break
  fi
done
if [[ -z "$RENODE_CANDIDATE" ]]; then
  RENODE_CANDIDATE="$(find "$USER_PREFIX" -maxdepth 3 -type f \( -name renode -o -name Renode \) -perm -111 2>/dev/null | head -n1 || true)"
fi

if [[ -z "$RENODE_CANDIDATE" || ! -x "$RENODE_CANDIDATE" ]]; then
  fatal "renode binary was not found after extracting portable package"
fi

ln -sfn "$RENODE_CANDIDATE" "$BIN_DIR_MANAGED/renode"

chown -R "$(id -u):$(id -g)" "$USER_PREFIX" || true
persist_path_entry "$BIN_DIR_MANAGED" "Added by SaxoFlow Renode installer"

if "$BIN_DIR_MANAGED/renode" --version >/dev/null 2>&1; then
  success "Renode installed successfully to $BIN_DIR_MANAGED"
  info "Detected version: $("$BIN_DIR_MANAGED/renode" --version 2>&1 | head -n1)"
else
  fatal "renode binary was not executable after installation"
fi
