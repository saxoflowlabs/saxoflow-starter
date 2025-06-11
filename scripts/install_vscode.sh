#!/bin/bash

set -e
source "$(dirname "$0")/check_deps.sh"

echo "🖥️ Installing Visual Studio Code..."

# Step 1: Install dependencies for VSCode repo management
check_deps wget gpg apt-transport-https software-properties-common

# Step 2: Add Microsoft GPG key only if not already present
if [ ! -f /usr/share/keyrings/packages.microsoft.gpg ]; then
    echo "🔑 Adding Microsoft GPG key..."
    wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor | sudo tee /usr/share/keyrings/packages.microsoft.gpg > /dev/null
else
    echo "ℹ️ Microsoft GPG key already installed."
fi

# Step 3: Add Microsoft VSCode repository only if not present
if [ ! -f /etc/apt/sources.list.d/vscode.list ]; then
    echo "📦 Adding VSCode repository..."
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/packages.microsoft.gpg] https://packages.microsoft.com/repos/vscode stable main" | sudo tee /etc/apt/sources.list.d/vscode.list
else
    echo "ℹ️ VSCode repository already present."
fi

# Step 4: Install VSCode
sudo apt update
sudo apt install -y code

# Step 5: Install HDL extensions idempotently
echo "🧩 Installing recommended HDL extensions..."

extensions=(
  "mshr-h.VerilogHDL"
  "ms-python.python"
  "ms-vscode.cpptools"
  "twxs.cmake"
)

for ext in "${extensions[@]}"; do
    if code --list-extensions | grep -q "$ext"; then
        echo "✅ Extension already installed: $ext"
    else
        echo "📦 Installing extension: $ext"
        code --install-extension "$ext" || echo "⚠️ Failed to install $ext"
    fi
done

echo "✅ VSCode and HDL extensions installed successfully!"
