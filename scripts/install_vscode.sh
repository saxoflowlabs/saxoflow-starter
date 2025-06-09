#!/bin/bash
set -e

echo "🖥️ Installing Visual Studio Code..."

# Step 1: Install VSCode via Microsoft package repository
sudo apt update
sudo apt install -y wget gpg apt-transport-https software-properties-common

# Add Microsoft GPG key and repo
wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > packages.microsoft.gpg
sudo install -o root -g root -m 644 packages.microsoft.gpg /usr/share/keyrings/
sudo sh -c 'echo "deb [arch=amd64 signed-by=/usr/share/keyrings/packages.microsoft.gpg] \
  https://packages.microsoft.com/repos/vscode stable main" > /etc/apt/sources.list.d/vscode.list'

sudo apt update
sudo apt install -y code

# Step 2: Install recommended extensions
echo "🧩 Installing recommended HDL extensions..."

code --install-extension mshr-h.VerilogHDL
code --install-extension hdlc.vscode-verilog-hdl-support
code --install-extension ms-python.python
code --install-extension ms-vscode.cpptools
code --install-extension twxs.cmake

echo "✅ VSCode and HDL extensions installed successfully!"
