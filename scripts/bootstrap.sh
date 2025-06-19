#!/usr/bin/env bash

# saxoflow/scripts/bootstrap.sh — Professional SaxoFlow Bootstrap

set -euo pipefail

# Load global paths and helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$ROOT_DIR/scripts/common/logger.sh"
source "$ROOT_DIR/scripts/common/paths.sh"
source "$ROOT_DIR/scripts/common/check_deps.sh"

info "🚀 SaxoFlow Professional Bootstrap Starting..."

# Ensure essential host system dependencies (minimal global setup)
check_deps python3 python3-venv python3-pip git

# ✅ Create essential SaxoFlow directory structure (safe idempotent)
mkdir -p "$TOOLS_DIR"

# ✅ Setup Python virtual environment if not already existing
if [ ! -d "$ROOT_DIR/.venv" ]; then
    info "🔧 Creating Python virtualenv at $ROOT_DIR/.venv..."
    python3 -m venv "$ROOT_DIR/.venv"
else
    info "ℹ️ Python virtualenv already exists — reusing..."
fi

# ✅ Activate virtualenv
source "$ROOT_DIR/.venv/bin/activate"

# ✅ Upgrade pip and install SaxoFlow Python package itself
info "📦 Installing SaxoFlow Python dependencies..."
pip install --upgrade pip

# Install saxoflow via editable mode (best for development)
pip install -e "$ROOT_DIR"

# ✅ Final message
info "✅ SaxoFlow Bootstrap completed successfully."
echo
echo "👉 Next steps:"
echo "   1️⃣ Activate environment:  source .venv/bin/activate"
echo "   2️⃣ Run environment setup: saxoflow init-env"
echo "   3️⃣ Install tools:          saxoflow install"
echo "   4️⃣ Verify:                saxoflow doctor"
echo
