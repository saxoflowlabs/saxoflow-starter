#!/bin/bash

set -e
source "$(dirname "$0")/check_deps.sh"

echo "🖥️ Installing Visual Studio Code..."

# Step 1: Install VSCode via Microsoft package repository
sudo apt update
sudo apt install -y wget gpg apt-transport-https software-properties-common

# Add Microsoft GPG key and repo
wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > packages.microsoft.gpg
sudo install -o root -g root -m 644 packages.microsoft.gpg /usr/share/keyrings/
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/packages.microsoft.gpg] https://packages.microsoft.com/repos/vscode stable main" | sudo tee /etc/apt/sources.list.d/vscode.list

sudo apt update
sudo apt install -y code

# Step 2: Install HDL extensions
echo "🧩 Installing recommended HDL extensions..."
code --install-extension mshr-h.VerilogHDL || echo "⚠️ Failed to install mshr-h.VerilogHDL"
code --install-extension ms-python.python || true
code --install-extension ms-vscode.cpptools || true
code --install-extension twxs.cmake || true

echo "✅ VSCode and HDL extensions installed successfully!"
