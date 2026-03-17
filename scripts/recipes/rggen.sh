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

info "Installing RgGen in a SaxoFlow-managed RubyGems environment..."

USER_PREFIX="$INSTALL_DIR/rggen"
BIN_DIR_MANAGED="$USER_PREFIX/bin"
GEM_HOME_DIR="$USER_PREFIX/gems"
GEM_BIN_DIR="$GEM_HOME_DIR/bin"

check_deps ruby ruby-dev

rm -rf "$USER_PREFIX"
mkdir -p "$BIN_DIR_MANAGED" "$GEM_HOME_DIR"

# Install RgGen from RubyGems into an isolated gem home under ~/.local/rggen.
GEM_HOME="$GEM_HOME_DIR" \
GEM_PATH="$GEM_HOME_DIR" \
gem install --no-document --bindir "$GEM_BIN_DIR" rggen rggen-systemverilog

# The generated gem stub needs GEM_HOME/GEM_PATH set; expose a stable wrapper.
cat > "$BIN_DIR_MANAGED/rggen" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
USER_PREFIX="$(cd "$SELF_DIR/.." && pwd)"
export GEM_HOME="$USER_PREFIX/gems"
export GEM_PATH="$USER_PREFIX/gems"
exec "$USER_PREFIX/gems/bin/rggen" "$@"
EOF
chmod +x "$BIN_DIR_MANAGED/rggen"


if [[ ! -x "$GEM_BIN_DIR/rggen" ]]; then
  fatal "rggen gem executable was not installed to $GEM_BIN_DIR"
fi

chown -R "$(id -u):$(id -g)" "$USER_PREFIX" || true

persist_path_entry "$BIN_DIR_MANAGED" "Added by SaxoFlow RgGen installer"

if "$BIN_DIR_MANAGED/rggen" --version >/dev/null 2>&1; then
  success "RgGen installed successfully to $BIN_DIR_MANAGED"
  info "Detected version: $($BIN_DIR_MANAGED/rggen --version 2>&1 | head -1)"
else
  fatal "rggen binary was not found after installation"
fi
