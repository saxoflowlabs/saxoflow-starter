#!/bin/bash
set -e

# Welcome
echo -e "\n🔧 SaxoFlow setup started..."

# Step 1: Create virtual environment
if [ ! -d ".venv" ]; then
  echo "📦 Creating virtual environment..."
  python3 -m venv .venv
fi

# Step 2: Activate it
source .venv/bin/activate

# Step 3: Install Python dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Step 4: Make CLI script executable
chmod +x bin/saxoflow

# Step 5: Link CLI commands globally (if not already)
if [ ! -L "/usr/local/bin/saxoflow" ]; then
  echo "⚙️ Linking saxoflow to /usr/local/bin/"
  sudo ln -s "$PWD/bin/saxoflow" /usr/local/bin/saxoflow
fi

if [ ! -L "/usr/local/bin/setup_saxoflow" ]; then
  echo "⚙️ Linking setup_saxoflow to /usr/local/bin/"
  sudo ln -s "$PWD/bin/setup_cli.sh" /usr/local/bin/setup_saxoflow
fi

# Onboarding Message
echo -e "\n✅ SaxoFlow setup complete!"
echo -e "\n🌟 Welcome to SaxoFlow — your digital design playground!"
echo -e "\n💡 \"Design isn't just syntax, it's how you *think* in logic.\""
echo "    — An RTL Engineer"
echo -e "\n🧠 SaxoFlow is built to make *you* think like silicon — one gate at a time."
echo "📐 From simulation to synthesis, from waveform debug to formal proof,"
echo "   you're now equipped with a clean, minimal, and powerful flow."
echo -e "\n🚀 Designed for students, researchers, and tinkerers — SaxoFlow helps"
echo "   you go from RTL to results without vendor lock-in or tool chaos."
echo -e "\n🎯 Ready to start your first project?"
echo "👉 Run: saxoflow init-env"
echo -e "\n🦾 Happy hacking — and remember: real logic is timeless."
