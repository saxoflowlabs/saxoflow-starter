#!/bin/bash

set -e
source "$(dirname "$0")/../common/logger.sh"
source "$(dirname "$0")/../common/paths.sh"
source "$(dirname "$0")/../common/check_deps.sh"

info "🖥 Installing Visual Studio Code..."

# ----------------------------------------
# Step 1: Ensure system dependencies for repo setup
# ----------------------------------------
check_deps wget gpg apt-transport-https software-properties-common

# ----------------------------------------
# Step 2: Add Microsoft repository (idempotent)
# ----------------------------------------
VSCODE_REPO_FILE="/etc/apt/sources.list.d/vscode.list"
GPG_FILE="/usr/share/keyrings/packages.microsoft.gpg"

if [ ! -f "$VSCODE_REPO_FILE" ]; then
    info "Adding Microsoft signing key..."
    wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > packages.microsoft.gpg
    sudo install -o root -g root -m 644 packages.microsoft.gpg "$GPG_FILE"
    rm packages.microsoft.gpg

    echo "deb [arch=amd64 signed-by=$GPG_FILE] https://packages.microsoft.com/repos/vscode stable main" | \
      sudo tee "$VSCODE_REPO_FILE"
else
    info "✅ VSCode repository already present."
fi

# ----------------------------------------
# Step 3: Install VSCode package itself
# ----------------------------------------
sudo apt update
sudo apt install -y code

# ----------------------------------------
# Step 4: Install VSCode extensions (safe re-run support)
# ----------------------------------------
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

info "✅ VSCode fully installed and extensions configured"
