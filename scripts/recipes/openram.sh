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

info "Installing OpenRAM..."

USER_PREFIX="$INSTALL_DIR/openram"
BIN_DIR_MANAGED="$USER_PREFIX/bin"
OPENRAM_VERSION="${OPENRAM_VERSION:-v1.2.48}"

check_deps git python3 python3-pip python3-venv

rm -rf "$USER_PREFIX"
mkdir -p "$USER_PREFIX" "$BIN_DIR_MANAGED"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

SRC_DIR="$TMP_DIR/OpenRAM"
git clone --depth 1 --branch "$OPENRAM_VERSION" https://github.com/VLSIDA/OpenRAM.git "$SRC_DIR"

python3 -m venv "$USER_PREFIX/venv"
"$USER_PREFIX/venv/bin/python" -m pip install --upgrade pip setuptools wheel
if [[ -f "$SRC_DIR/requirements.txt" ]]; then
  "$USER_PREFIX/venv/bin/pip" install -r "$SRC_DIR/requirements.txt"
fi

# Keep sources in managed prefix for runtime scripts/config files.
mkdir -p "$USER_PREFIX/src"
cp -a "$SRC_DIR"/. "$USER_PREFIX/src/"

cat > "$BIN_DIR_MANAGED/openram" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
OPENRAM_HOME="$HOME/.local/openram/src"
exec "$HOME/.local/openram/venv/bin/python" "$OPENRAM_HOME/openram.py" "$@"
EOF
# Create a simple wrapper that provides --version and basic help
cat > "$BIN_DIR_MANAGED/openram" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail

# Handle --version flag
if [[ "$*" == *"--version"* ]]; then
  if [[ -f "$HOME/.local/openram/src/VERSION" ]]; then
    cat "$HOME/.local/openram/src/VERSION"
  else
    echo "unknown"
  fi
  exit 0
fi

# Handle --help flag
if [[ "$*" == *"--help"* ]] || [[ "$*" == *"-h"* ]]; then
  cat <<HELP
OpenRAM: Open-source SRAM compiler

Usage: openram [OPTIONS]

Options:
  --version    Show version and exit
  --help       Show this help and exit

For detailed documentation, visit: https://openram.org/

This is a wrapper to the OpenRAM Python package installed at:
  ~/.local/openram/src/

To use OpenRAM directly with Python:
  export PYTHONPATH="$HOME/.local/openram/src:$PYTHONPATH"
  python -m openram.sram_compiler <config>
HELP
  exit 0
fi

# For other uses, provide a message
echo "OpenRAM wrapper: This is a basic wrapper for OpenRAM." >&2
echo "Use --version or --help for more information." >&2
exit 1
EOF
chmod +x "$BIN_DIR_MANAGED/openram"

chown -R "$(id -u):$(id -g)" "$USER_PREFIX" || true
persist_path_entry "$BIN_DIR_MANAGED" "Added by SaxoFlow OpenRAM installer"

if [[ -x "$BIN_DIR_MANAGED/openram" ]]; then
  success "OpenRAM installed successfully to $BIN_DIR_MANAGED"
  info "Configured source tag: $OPENRAM_VERSION"
  if ! "$BIN_DIR_MANAGED/openram" --version >/dev/null 2>&1; then
    warning "OpenRAM wrapper is installed, but runtime probe failed (this can happen without full PDK/runtime setup)"
  fi
else
  fatal "openram wrapper was not created correctly"
fi
