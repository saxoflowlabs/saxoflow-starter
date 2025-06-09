#!/bin/bash
set -e

echo "📦 Installing OpenROAD from source..."

# Step 1: Install dependencies
sudo apt update
sudo apt install -y \
  build-essential cmake g++ python3 python3-pip \
  libboost-all-dev libeigen3-dev flex bison tcl-dev tk-dev \
  libffi-dev libspdlog-dev libcurl4-openssl-dev \
  libyaml-cpp-dev libreadline-dev git

# Step 2: Clone OpenROAD (if not already cloned)
if [ -d "$HOME/OpenROAD" ]; then
  echo "⚠️  Directory '$HOME/OpenROAD' already exists. Please remove it to reinstall."
  exit 1
fi

git clone --recursive https://github.com/The-OpenROAD-Project/OpenROAD.git "$HOME/OpenROAD"
cd "$HOME/OpenROAD"

# Step 3: Build
mkdir -p build && cd build
cmake .. -DCMAKE_INSTALL_PREFIX="$HOME/.local"
make -j$(nproc)
make install

# Step 4: Add to PATH if not already
if ! grep -q 'export PATH="$HOME/.local/bin:$PATH"' ~/.bashrc; then
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "✅ OpenROAD installed successfully!"
echo "👉 Make sure to restart your terminal or run: source ~/.bashrc"
