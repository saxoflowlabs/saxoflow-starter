#!/bin/bash
set -euo pipefail

# -------------------------------------
# SaxoFlow One-Time Setup Script
# -------------------------------------
# Usage: Run once after git clone
# It sets up CLI entrypoints and boots Python env

# Ensure we're in the root directory
cd "$(dirname "$0")/.."

# 1️⃣ Make CLI scripts executable
chmod +x bin/saxoflow
chmod +x bin/launch_saxoflow

# 2️⃣ Bootstrap Python virtualenv
echo "📦 Bootstrapping Python virtualenv..."
python3 scripts/bootstrap_venv.py

# 3️⃣ Launch SaxoFlow startup CLI
echo "🚀 Launching SaxoFlow..."
./bin/launch_saxoflow
