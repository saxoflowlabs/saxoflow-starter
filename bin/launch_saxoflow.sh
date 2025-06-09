#!/bin/bash
set -e

# -------------------------------
# SaxoFlow CLI Bootstrap Script
# -------------------------------
echo -e "\n🔧 SaxoFlow setup started..."

# Detect shell config file (.bashrc or .zshrc)
SHELL_RC="$HOME/.bashrc"
[[ "$SHELL" == */zsh ]] && SHELL_RC="$HOME/.zshrc"

# Step 1: Create virtual environment
if [ ! -d ".venv" ]; then
  echo "📦 Creating Python virtual environment at .venv/"
  python3 -m venv .venv
else
  echo "ℹ️  Virtual environment already exists, skipping creation."
fi

# Step 2: Activate virtualenv
source .venv/bin/activate

# Step 3: Install Python dependencies
echo "📥 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Step 4: Ensure CLI scripts are executable
chmod +x "$PWD/bin/saxoflow"
chmod +x "$PWD/bin/launch_saxoflow"

# Step 5: Link CLI globally
if [ ! -L "/usr/local/bin/saxoflow" ]; then
  echo "⚙️ Linking saxoflow to /usr/local/bin/"
  sudo ln -s "$PWD/bin/saxoflow" /usr/local/bin/saxoflow
fi

if [ ! -L "/usr/local/bin/launch_saxoflow" ]; then
  echo "⚙️ Linking launch_saxoflow to /usr/local/bin/"
  sudo ln -s "$PWD/bin/launch_saxoflow" /usr/local/bin/launch_saxoflow
fi

# Step 6: Add auto-activation of virtualenv to future shells
if ! grep -q "source \"$PWD/.venv/bin/activate\"" "$SHELL_RC"; then
  echo "source \"$PWD/.venv/bin/activate\"" >> "$SHELL_RC"
  echo "✅ Auto-activation added to $SHELL_RC"
fi

# -------------------------------
# Final Welcome Message
# -------------------------------
echo -e "\n✅ SaxoFlow setup complete!"
echo -e "\n🌟 Welcome to SaxoFlow — your digital design playground!"
echo -e "\n💡 \"Design isn't just syntax, it's how you *think* in logic.\""
echo "    — An RTL Engineer"
echo -e "\n📐 From simulation to synthesis, waveform debug to formal proofs,"
echo "   you're now equipped with a clean, modular, and powerful flow."
echo -e "\n🚀 Run: saxoflow init-env"
echo "🧠  Then: saxoflow init my_project"
echo -e "\n🦾 Happy hacking — and remember: real logic is timeless."

# Step 7: Warn if current shell doesn't have PATH yet
if ! command -v saxoflow &>/dev/null; then
  echo -e "\n⚠️  'saxoflow' not found in current shell."
  echo "👉 Run: source $SHELL_RC"
fi
