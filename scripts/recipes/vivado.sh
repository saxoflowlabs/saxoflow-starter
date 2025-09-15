#!/usr/bin/env bash
# scripts/install/vivado.sh — Vivado WebPACK Auto-Installer Helper (Linux only)

set -euo pipefail

INSTALLER_URL="https://www.xilinx.com/support/download.html"
INSTALLER_FILE=$(ls Xilinx_Unified_Installer-*.tar.gz 2>/dev/null || true)
INSTALLER_EXTRACTED_DIR="Xilinx_Unified_Installer"
DEFAULT_INSTALL_DIR="/opt/Xilinx/Vivado"

echo "Vivado WebPACK Installer (Linux)"

# ---------------------------------------------
# 1. Check if Vivado is already in PATH
# ---------------------------------------------
if command -v vivado &>/dev/null; then
    echo "[✅] Vivado is already installed at: $(which vivado)"
    exit 0
fi

# ---------------------------------------------
# 2. Verify OS
# ---------------------------------------------
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo "[❌] This script only supports Linux for now."
    echo "➡ Please download manually from:"
    echo "   $INSTALLER_URL"
    exit 1
fi

# ---------------------------------------------
# 3. Locate installer or prompt download
# ---------------------------------------------
if [[ -z "$INSTALLER_FILE" ]]; then
    echo "Vivado WebPACK installer not found in current directory."
    echo "Please download it from:"
    echo "   $INSTALLER_URL"
    echo "Choose: 'Linux Self Extracting Web Installer'"
    echo
    echo "[⬇️] After downloading, place the installer TAR file in this folder and rerun this script."
    exit 1
fi

# ---------------------------------------------
# 4. Extract installer tarball
# ---------------------------------------------
echo "Extracting: $INSTALLER_FILE"
tar -xzf "$INSTALLER_FILE"

cd "$INSTALLER_EXTRACTED_DIR"

# Ask user for install location (default /opt/Xilinx/Vivado)
read -rp "[📂] Enter Vivado install path [default: $DEFAULT_INSTALL_DIR]: " CUSTOM_DIR
INSTALL_PATH="${CUSTOM_DIR:-$DEFAULT_INSTALL_DIR}"

# ---------------------------------------------
# 5. Run xsetup in GUI (user will pick version)
# ---------------------------------------------
echo "⚙ Launching Vivado GUI installer..."
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
    if ! grep -q "$VIVADO_BIN" ~/.bashrc; then
        echo "export PATH=\"$VIVADO_BIN:\$PATH\"" >> ~/.bashrc
        echo "[✅] Added Vivado to PATH via ~/.bashrc"
    else
        echo "[✅] Vivado already in PATH"
    fi
else
    echo "[⚠] Could not detect Vivado install directory at: $INSTALL_PATH"
    echo "[👉] Please add your Vivado bin path manually to ~/.bashrc"
    exit 1
fi

echo
echo "🎉 Vivado installation helper completed."
echo "📢 Please run: source ~/.bashrc"
