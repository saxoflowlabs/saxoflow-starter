#!/bin/bash

set -euo pipefail

# shellcheck source=/dev/null
source "$(dirname "$0")/../common/logger.sh"
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/paths.sh"
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/check_deps.sh"

# Optional: enable shell xtrace only when explicitly requested, and log it to the logfile
if [[ "${SAXOFLOW_DEBUG:-0}" == "1" ]]; then
  # Send xtrace to the same logfile used by logger.sh (descriptor 3)
  if [[ -n "${LOGFILE:-}" ]]; then
    exec 3>>"$LOGFILE"
    export BASH_XTRACEFD=3
  fi
  export PS4='+ ${BASH_SOURCE##*/}:${LINENO}: '
  set -x
fi

info "Installing Visual Studio Code..."

# --------------------------------------------------
# OS Detection Logic
# --------------------------------------------------

# Detect if we are inside WSL
if grep -qEi "(Microsoft|WSL)" /proc/version &> /dev/null; then
    info "Detected WSL environment."

    # Check if Windows VSCode exists
    if powershell.exe -Command "Get-Command code.cmd" &> /dev/null; then
        info "VSCode detected on Windows host."
        info "Please ensure you have the 'WSL Remote' extension installed in Windows VSCode."
        info "You can run: code . from inside WSL once the WSL extension is installed."
    else
        warn "VSCode not detected on Windows host. Please install VSCode for Windows from https://code.visualstudio.com"
    fi

    # Exit installer — do not install VSCode via apt inside WSL
    exit 0
fi

# --------------------------------------------------
# Native Linux (Ubuntu/Debian) path
# --------------------------------------------------

info "Detected native Linux environment. Proceeding with system install."

# Step 1: Install system dependencies for repo setup
check_deps wget gpg apt-transport-https software-properties-common

# Step 2: Add Microsoft repository (idempotent)
VSCODE_REPO_FILE="/etc/apt/sources.list.d/vscode.list"
GPG_FILE="/usr/share/keyrings/packages.microsoft.gpg"

if [ ! -f "$VSCODE_REPO_FILE" ]; then
    info "Adding Microsoft signing key..."
    wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > packages.microsoft.gpg
    sudo install -o root -g root -m 644 packages.microsoft.gpg "$GPG_FILE"
    rm packages.microsoft.gpg

    echo "deb [arch=amd64 signed-by=$GPG_FILE] https://packages.microsoft.com/repos/vscode stable main" | \
      sudo tee "$VSCODE_REPO_FILE" >/dev/null
else
    info "VSCode repository already present."
fi

# Step 3: Install VSCode via apt
sudo apt update
sudo apt install -y code

# Step 4: Install VSCode extensions (safe re-run support)
info "Installing VSCode extensions..."

EXTS=(
  mshr-h.VerilogHDL
  ms-python.python
  ms-vscode.cpptools
  twxs.cmake
)

for ext in "${EXTS[@]}"; do
  code --install-extension "$ext" || warn "Extension $ext failed to install."
done

info "VSCode fully installed and extensions configured."
