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

info "Installing SiliconCompiler..."

USER_PREFIX="$INSTALL_DIR/siliconcompiler"
BIN_DIR_MANAGED="$USER_PREFIX/bin"

check_deps python3 python3-pip python3-venv

rm -rf "$USER_PREFIX"
python3 -m venv "$USER_PREFIX"

"$BIN_DIR_MANAGED/python" -m pip install --upgrade pip setuptools wheel
"$BIN_DIR_MANAGED/python" -m pip install siliconcompiler

# Recent SiliconCompiler versions expose `smake` plus sc-* helpers.
# Normalize to a stable `sc` launcher for SaxoFlow.
if [[ ! -x "$BIN_DIR_MANAGED/sc" ]]; then
  if [[ -x "$BIN_DIR_MANAGED/smake" ]]; then
    ln -sfn "$BIN_DIR_MANAGED/smake" "$BIN_DIR_MANAGED/sc"
  else
    cat > "$BIN_DIR_MANAGED/sc" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
exec "$HOME/.local/siliconcompiler/bin/python" -m siliconcompiler "$@"
EOF
    chmod +x "$BIN_DIR_MANAGED/sc"
  fi
fi

chown -R "$(id -u):$(id -g)" "$USER_PREFIX" || true
persist_path_entry "$BIN_DIR_MANAGED" "Added by SaxoFlow SiliconCompiler installer"

if "$BIN_DIR_MANAGED/python" -c "import importlib.metadata as m; print(m.version('siliconcompiler'))" >/dev/null 2>&1; then
  success "SiliconCompiler installed successfully to $BIN_DIR_MANAGED"
  info "Detected version: $("$BIN_DIR_MANAGED/python" -c "import importlib.metadata as m; print(m.version('siliconcompiler'))" 2>/dev/null || echo unknown)"
else
  fatal "siliconcompiler Python package was not found after installation"
fi
