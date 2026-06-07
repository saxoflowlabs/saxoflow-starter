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

info "Installing NetlistSVG..."

PREFIX="$INSTALL_DIR/netlistsvg"
BIN_DIR="$PREFIX/bin"
mkdir -p "$BIN_DIR"

resolve_node_toolchain() {
  if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
    info "Using Node.js from PATH: $(command -v node)"
    return 0
  fi

  local nvm_root="${NVM_DIR:-$HOME/.nvm}"
  local candidate=""
  if [[ -d "$nvm_root/versions/node" ]]; then
    candidate="$(
      find "$nvm_root/versions/node" \
        -mindepth 2 -maxdepth 2 -type d -name bin -print 2>/dev/null \
        | sort -V \
        | tail -n 1
    )"
  fi
  if [[ -n "$candidate" && -x "$candidate/node" && -x "$candidate/npm" ]]; then
    export PATH="$candidate:$PATH"
    info "Using Node.js from NVM: $candidate/node"
    return 0
  fi

  info "Node.js was not found in PATH or an existing NVM installation."
  check_deps nodejs npm

  if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
    fatal "Node.js and npm are required, but installation did not provide both commands."
  fi
}

resolve_node_toolchain

npm install --prefix "$PREFIX" --no-audit --no-fund netlistsvg@latest
ln -sfn ../node_modules/.bin/netlistsvg "$BIN_DIR/netlistsvg"
chmod +x "$BIN_DIR/netlistsvg"

NETLISTSVG_HELP="$("$BIN_DIR/netlistsvg" --help 2>&1 || true)"
if ! grep -qiE 'usage:.*netlistsvg|input_json_file' <<<"$NETLISTSVG_HELP"; then
  fatal "NetlistSVG installation verification failed."
fi

persist_path_entry "$BIN_DIR" "Added by SaxoFlow NetlistSVG installer"
success "NetlistSVG installed at $BIN_DIR/netlistsvg"
