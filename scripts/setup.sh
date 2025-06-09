#!/bin/bash
set -e

echo "🔒 Creating virtual Python environment for SaxoFlow..."

# Create and activate venv
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate

echo "📦 Installing Python dependencies into virtualenv..."
pip install --upgrade pip
pip install -r requirements.txt

# Add saxoflow to PATH if not already
if [[ ":$PATH:" != *":$PWD/bin:"* ]]; then
  echo "export PATH=\"$PWD/bin:\$PATH\"" >> ~/.bashrc
  export PATH="$PWD/bin:$PATH"
fi

# Optional: auto-activate venv in new shells
if ! grep -q "$PWD/.venv/bin/activate" ~/.bashrc; then
  echo "source \"$PWD/.venv/bin/activate\"" >> ~/.bashrc
fi

chmod +x bin/saxoflow

echo "✅ SaxoFlow CLI environment is ready."
echo "👉 To activate: source .venv/bin/activate"
echo "👉 To use CLI: saxoflow init-env"
echo "ℹ️  Restart terminal or run 'source ~/.bashrc' to finalize environment setup."
