#!/bin/bash

set -e
source "$(dirname "$0")/../common/logger.sh"
source "$(dirname "$0")/../common/paths.sh"
source "$(dirname "$0")/../common/check_deps.sh"

info "🖥 Installing Visual Studio Code..."

# ----------------------------------------
# Step 1: Dependencies for repo setup
# ----------------------------------------
check_deps wget gpg apt-transport-https software-properties-common

# ----------------------------------------
# Step 2: Add VSCode repository if not already present
# ----------------------------------------
VSCODE_REPO_FILE="/etc/apt/sources.list.d/vscode.list"

if [ ! -f "$VSCODE_REPO_FILE" ]; then
    info "Adding Microsoft GPG key and repository..."
    wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > packages.microsoft.gpg
    sudo install -o root -g root -m 644 packages.microsoft.gpg /usr/share/keyrings/
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/packages.microsoft.gpg] https://packages.microsoft.com/repos/vscode stable main" | \
      sudo tee "$VSCODE_REPO_FILE"
else
    info "VSCode repo already exists, skipping repository setup."
fi

# ----------------------------------------
# Step 3: Install VSCode package
# ----------------------------------------
sudo apt update
sudo apt install -y code

# ----------------------------------------
# Step 4: Install extensions (safe repeated installs)
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

info "✅ VSCode installed and configured successfully"
