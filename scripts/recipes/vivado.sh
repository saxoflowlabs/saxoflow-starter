#!/usr/bin/env bash
# scripts/install/vivado.sh — Vivado WebPACK Auto-Installer Helper (Linux only)

set -euo pipefail

# shellcheck source=/dev/null
source "$(dirname "$0")/../common/persist_path.sh"

INSTALLER_URL="https://www.xilinx.com/support/download.html"
INSTALLER_FILE=$(ls Xilinx_Unified_Installer-*.tar.gz 2>/dev/null || true)
INSTALLER_EXTRACTED_DIR="Xilinx_Unified_Installer"
DEFAULT_INSTALL_DIR="/opt/Xilinx/Vivado"

# ---------- simple colored loggers (ASCII-only) ----------
RED="\033[1;31m"; YELLOW="\033[1;33m"; GREEN="\033[1;32m"; CYAN="\033[1;36m"; NC="\033[0m"
info()    { echo -e "${CYAN}INFO:    $*${NC}"; }
warn()    { echo -e "${YELLOW}WARNING: $*${NC}"; }
error()   { echo -e "${RED}ERROR:   $*${NC}"; }
success() { echo -e "${GREEN}SUCCESS: $*${NC}"; }

info "Vivado WebPACK Installer (Linux)"

# ---------------------------------------------
# 1. Check if Vivado is already in PATH
# ---------------------------------------------
if command -v vivado &>/dev/null; then
    success "Vivado is already installed at: $(command -v vivado)"
    exit 0
fi

# ---------------------------------------------
# 2. Verify OS
# ---------------------------------------------
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    error "This script only supports Linux for now."
    info "Please download manually from:"
    info "   $INSTALLER_URL"
    exit 1
fi

# ---------------------------------------------
# 3. Locate installer or prompt download
# ---------------------------------------------
if [[ -z "$INSTALLER_FILE" ]]; then
    warn "Vivado WebPACK installer not found in the current directory."
    info "Please download it from:"
    info "   $INSTALLER_URL"
    info "Choose: 'Linux Self Extracting Web Installer'"
    echo
    info "After downloading, place the installer TAR file in this folder and rerun this script."
    exit 1
fi

# ---------------------------------------------
# 4. Extract installer tarball
# ---------------------------------------------
info "Extracting: $INSTALLER_FILE"
tar -xzf "$INSTALLER_FILE"

cd "$INSTALLER_EXTRACTED_DIR"

# Ask user for install location (default /opt/Xilinx/Vivado)
read -rp "Enter Vivado install path [default: $DEFAULT_INSTALL_DIR]: " CUSTOM_DIR
INSTALL_PATH="${CUSTOM_DIR:-$DEFAULT_INSTALL_DIR}"

# ---------------------------------------------
# 5. Run xsetup in GUI (user will pick version)
# ---------------------------------------------
info "Launching Vivado GUI installer..."
chmod +x xsetup
./xsetup

# ---------------------------------------------
# 6. Detect installed Vivado version
# ---------------------------------------------
LATEST_VIVADO_PATH=$(find "$INSTALL_PATH" -maxdepth 1 -type d -name "20*" | sort -Vr | head -n1)
VIVADO_BIN="${LATEST_VIVADO_PATH}/bin"

# ---------------------------------------------
# 7. Add Vivado to PATH (in .bashrc)
# ---------------------------------------------
if [[ -d "$VIVADO_BIN" ]]; then
    persist_path_entry "$VIVADO_BIN" "Added by SaxoFlow vivado installer"
else
    warn "Could not detect Vivado install directory at: $INSTALL_PATH"
    exit 1
fi

echo
success "Vivado installation helper completed."
info "Restart your terminal or source your shell rc file to pick up Vivado in PATH."
