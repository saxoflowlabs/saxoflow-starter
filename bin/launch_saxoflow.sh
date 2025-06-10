# Deprecated: Use python3 main.py instead


#!/bin/bash
set -e

# ----------------------------------------
# 🚀 SaxoFlow: One-Step Setup Script
# ----------------------------------------

echo -e "\n🔧 SaxoFlow setup started..."

# Detect shell config file
SHELL_RC="$HOME/.bashrc"
[[ "$SHELL" == */zsh ]] && SHELL_RC="$HOME/.zshrc"

# Step 1: Create Python virtual environment if missing
if [ ! -d ".venv" ]; then
  echo "📦 Creating Python virtual environment at .venv/"
  python3 -m venv .venv
else
  echo "ℹ️  Virtual environment already exists. Skipping creation."
fi

# Step 2: Activate virtualenv
source .venv/bin/activate

# Step 3: Install Python dependencies
echo "📥 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Step 4: Ensure CLI launcher is executable
if [ -f "bin/saxoflow" ]; then
  chmod +x bin/saxoflow
  echo "✅ Made bin/saxoflow executable"
else
  echo "❌ Error: bin/saxoflow not found!"
  echo "   Please ensure it's present and contains:"
  echo '   #!/usr/bin/env python3\n   from saxoflow.cli import cli\n   cli()'
  exit 1
fi

# Step 5: Ensure this script is also executable (for future clones)
chmod +x bin/launch_saxoflow.sh

# Step 6: Create global symlinks for CLI tools
if ! command -v saxoflow &>/dev/null; then
  echo "⚙️ Linking saxoflow to /usr/local/bin (requires sudo)"
  sudo ln -sf "$PWD/bin/saxoflow" /usr/local/bin/saxoflow
fi

if ! command -v launch_saxoflow &>/dev/null; then
  echo "⚙️ Linking launch_saxoflow to /usr/local/bin (requires sudo)"
  sudo ln -sf "$PWD/bin/launch_saxoflow.sh" /usr/local/bin/launch_saxoflow
fi

# Step 7: Auto-activate venv in future shells
if ! grep -q "source \"$PWD/.venv/bin/activate\"" "$SHELL_RC"; then
  echo "source \"$PWD/.venv/bin/activate\"" >> "$SHELL_RC"
  echo "✅ Auto-activation added to $SHELL_RC"
fi

# ----------------------------------------
# ✅ Success Message
# ----------------------------------------

echo -e "\n✅ SaxoFlow CLI environment is ready!"
echo -e "\n🌟 Welcome to SaxoFlow — your open digital design playground!"
echo -e "\n💡 \"Design isn't just syntax, it's how you *think* in logic.\""
echo "    — An RTL Engineer"
echo -e "\n📐 From simulation to synthesis, waveform debug to formal proofs,"
echo "   you're now equipped with a clean, modular, and powerful flow."
echo -e "\n🚀 Run: saxoflow init-env"
echo "🧠  Then: saxoflow init my_project"
echo -e "\n🦾 Happy hacking — and remember: real logic is timeless."

# Step 8: Warn if shell needs restart
if ! command -v saxoflow &>/dev/null; then
  echo -e "\n⚠️  saxoflow command not yet in this shell session."
  echo "👉 Run: source $SHELL_RC"
fi
