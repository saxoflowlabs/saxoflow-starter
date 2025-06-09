#!/bin/bash
set -e

echo "📦 Installing Verilator..."

sudo apt install -y autoconf g++ flex bison libfl2 libfl-dev \
  zlib1g-dev libgoogle-perftools-dev numactl perl python3 make git

if [ -d "verilator" ]; then
  echo "⚠️  Directory 'verilator' already exists. Please delete or rename it before continuing."
  exit 1
fi

git clone --depth 1 --branch stable https://github.com/verilator/verilator.git
cd verilator
autoconf
./configure
make -j$(nproc)
sudo make install

echo "✅ Verilator ready"
