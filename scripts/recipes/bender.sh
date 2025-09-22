#!/usr/bin/env bash
set -xuo pipefail
set -e

# Common helpers (same as your verilator recipe)
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/logger.sh"
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/paths.sh"
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/check_deps.sh"

info "Installing Bender (HDL dependency manager)..."

# Ensure tools dir exists (parity with verilator recipe)
mkdir -p "$TOOLS_DIR"
cd "$TOOLS_DIR"

# Install prefix managed by SaxoFlow
USER_PREFIX="$INSTALL_DIR/bender"
BIN_DIR_MANAGED="$USER_PREFIX/bin"
mkdir -p "$BIN_DIR_MANAGED"

# Preferred method can be passed as arg: "cargo" or "binary"
METHOD="${1:-binary}"

install_with_cargo() {
  info "Method: cargo (managed prefix: $USER_PREFIX)"
  check_deps cargo
  # --root lets us install into our managed prefix (no sudo, reproducible)
  cargo install --locked --root "$USER_PREFIX" bender
  # cargo guarantees binary at $USER_PREFIX/bin/bender
  info "Installed: $("$BIN_DIR_MANAGED/bender" --version)"
}

install_with_binary() {
  info "Method: binary (upstream one-liner -> copy under managed prefix)"
  check_deps curl

  # Run upstream installer (writes to ~/.local/bin by default; some versions
  # drop the binary in the current working directory instead)
  curl --proto '=https' --tlsv1.2 https://pulp-platform.github.io/bender/init -sSf | sh

  # Candidate locations to look for the freshly installed binary
  CANDIDATES=()
  CANDIDATES+=("$HOME/.local/bin/bender")
  # In PATH?
  if command -v bender >/dev/null 2>&1; then
    CANDIDATES+=("$(command -v bender)")
  fi
  # Current dir (tools-src) fallback – upstream sometimes installs here
  CANDIDATES+=("$PWD/bender" "$TOOLS_DIR/bender")

  LOCAL_BIN=""
  for c in "${CANDIDATES[@]}"; do
    if [[ -n "$c" && -x "$c" ]]; then
      LOCAL_BIN="$c"
      break
    fi
  done

  # As a last resort, scan a couple of common places quickly
  if [[ -z "$LOCAL_BIN" ]]; then
    set +e
    FOUND="$(find "$TOOLS_DIR" "$HOME/.local/bin" -maxdepth 2 -type f -perm -u+x -name 'bender*' 2>/dev/null | head -n1)"
    set -e
    if [[ -n "$FOUND" ]]; then
      LOCAL_BIN="$FOUND"
    fi
  fi

  if [[ -z "$LOCAL_BIN" ]]; then
    error "Bender binary not found after install (checked ~/.local/bin, PATH, tools-src). Aborting."
    exit 1
  fi

  # Copy to SaxoFlow-managed location
  cp -f "$LOCAL_BIN" "$BIN_DIR_MANAGED/bender"
  chmod +x "$BIN_DIR_MANAGED/bender"
  info "Installed: $("$BIN_DIR_MANAGED/bender" --version)"
}

# Choose method
case "$METHOD" in
  cargo)  install_with_cargo ;;
  binary) install_with_binary ;;
  *)
    error "Usage: $0 [binary|cargo]"
    exit 2
    ;;
esac

# Fix ownership (parity with verilator)
chown -R "$(id -u):"$(id -g)"" "$USER_PREFIX" || true

# Optionally expose via a global managed bin dir if your paths.sh defines one
if [[ -n "${BIN_DIR:-}" ]]; then
  mkdir -p "$BIN_DIR"
  ln -sf "$BIN_DIR_MANAGED/bender" "$BIN_DIR/bender"
  info "Linked $BIN_DIR/bender -> $BIN_DIR_MANAGED/bender"
fi

# Best-effort PATH hint for interactive shells if no BIN_DIR:
if [[ -z "${BIN_DIR:-}" ]]; then
  if ! grep -q 'export PATH="$HOME/.local/bin:$PATH"' "${HOME}/.bashrc" 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "${HOME}/.bashrc"
  fi
  if ! grep -q "export PATH=\"$USER_PREFIX/bin:\$PATH\"" "${HOME}/.bashrc" 2>/dev/null; then
    echo "export PATH=\"$USER_PREFIX/bin:\$PATH\"" >> "${HOME}/.bashrc"
  fi
fi

info "Bender installed to $USER_PREFIX/bin"
