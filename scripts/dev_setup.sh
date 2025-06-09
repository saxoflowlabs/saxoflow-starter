#!/bin/bash
set -e

# Detect shell config file
SHELL_RC="$HOME/.bashrc"
if [[ "$SHELL" == */zsh ]]; then
  SHELL_RC="$HOME/.zshrc"
fi

echo "🔒 Creating virtual Python environment for SaxoFlow..."

# Step 1: Create virtualenv if not present
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
  echo "✅ Virtual environment created at .venv/"
else
  echo "ℹ️  Virtual environment already exists, skipping creation."
fi

# Step 2: Activate virtualenv
source .venv/bin/activate

# Step 3: Install Python dependencies
echo "📦 Installing Python dependencies into virtualenv..."
pip install --upgrade pip
pip install -r requirements.txt

# Step 4: Add bin/ to PATH in shell config if not already added
if ! grep -q 'export PATH=.*bin' "$SHELL_RC"; then
  echo "export PATH=\"$PWD/bin:\$PATH\"" >> "$SHELL_RC"
  export PATH="$PWD/bin:$PATH"
  echo "✅ Added bin/ to PATH in $SHELL_RC"
else
  echo "ℹ️  bin/ already in PATH"
fi

# Step 5: Auto-activate venv in future shells
if ! grep -q ".venv/bin/activate" "$SHELL_RC"; then
  echo "source \"$PWD/.venv/bin/activate\"" >> "$SHELL_RC"
  echo "✅ Added auto-activation of virtualenv to $SHELL_RC"
else
  echo "ℹ️  Virtualenv auto-activation already present"
fi

# Step 6: Ensure CLI script is executable
chmod +x bin/saxoflow

# Step 7: Optional Git chmod
if git ls-files --error-unmatch scripts/dev_setup.sh &>/dev/null; then
  git update-index --chmod=+x scripts/dev_setup.sh
fi

# Step 8: Final welcome message
echo ""
echo "✅ SaxoFlow CLI environment is ready!"
echo ""
echo "🌟 Welcome to SaxoFlow — your open digital design flow."
echo ""
echo "💡 \"Design isn't just syntax, it's how you *think* in logic.\""
echo "    — An RTL Engineer"
echo ""
echo "📐 From simulation to synthesis, from waveform debug to formal proof,"
echo "   you're now equipped with a clean, minimal, and powerful RTL flow."
echo ""
echo "🚀 Run 'saxoflow init-env' to configure your toolchain."
echo "🧠 Build projects with 'saxoflow init my_project'"
echo ""
echo "🦾 Happy hacking — and remember: real logic is timeless."

# Step 9: Warn user if saxoflow is not yet recognized
if ! command -v saxoflow &>/dev/null; then
  echo ""
  echo "⚠️  'saxoflow' not found in current shell. Run:"
  echo "   source $SHELL_RC"
fi
