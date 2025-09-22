set -euo pipefail

# Unified SaxoFlow logger (colored levels: INFO/WARNING/ERROR/SUCCESS)
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/logger.sh"

YOSYS_REPO="https://github.com/YosysHQ/yosys.git"
SLANG_REPO="https://github.com/povik/yosys-slang.git"
TOOLS_SRC="$HOME/tools-src"
YOSYS_SRC="$TOOLS_SRC/yosys"
SLANG_SRC="$TOOLS_SRC/yosys-slang"
YOSYS_PREFIX="$HOME/.local/yosys"
# This is the correct directory for plugins relative to your Yosys install
YOSYS_PLUGINS_DIR="$YOSYS_PREFIX/share/yosys/plugins"

# ---- Dependencies ----
info "Checking dependencies (cmake, gcc, g++, make, flex, bison, ...)"
sudo apt-get update
sudo apt-get install -y cmake g++ gcc make flex bison libreadline-dev tcl-dev libffi-dev libboost-all-dev zlib1g zlib1g-dev python3 python3-pip git

mkdir -p "$TOOLS_SRC"
cd "$TOOLS_SRC"

# ---- Step 1: Clone and Build Yosys ----
if [ ! -d "$YOSYS_SRC" ]; then
    info "Cloning Yosys..."
    git clone --depth=1 "$YOSYS_REPO" "$YOSYS_SRC"
fi
cd "$YOSYS_SRC"
info "Updating Yosys..."
# Using 'git pull || true' is safer in automation
git pull --ff-only || true
git checkout main || true
git submodule update --init --recursive

info "Building Yosys..."
make -j"$(nproc)"
info "Installing Yosys to $YOSYS_PREFIX..."
make install PREFIX="$YOSYS_PREFIX"
cd "$TOOLS_SRC"

# Ensure yosys is in PATH for subsequent commands in THIS SCRIPT
export PATH="$YOSYS_PREFIX/bin:$PATH"

# ---- Step 2: Clone and Build Slang as a Yosys plugin ----
if [ ! -d "$SLANG_SRC" ]; then
    info "Cloning yosys-slang..."
    git clone --recursive "$SLANG_REPO" "$SLANG_SRC"
fi
cd "$SLANG_SRC"
info "Updating yosys-slang..."
git pull --ff-only || true
git submodule update --init --recursive

info "Building slang plugin for Yosys with CMake..."

# Remove any previous build
rm -rf build
mkdir build
cd build

# CMake step: tell it where Yosys sources are!
# We don't need CMAKE_INSTALL_PREFIX here as we will copy the plugin manually
cmake .. \
    -DYOSYS_SRC_DIR="$YOSYS_SRC" \
    -DCMAKE_CXX_FLAGS="-I$YOSYS_SRC/kernel -I$YOSYS_SRC/frontends -I$YOSYS_SRC"

info "Compiling the slang plugin..."
cmake --build . -j"$(nproc)"

# ---- Step 3: Manually Install the Plugin ----
info "Installing slang plugin manually..."

# The actual .so location is in the build directory
PLUGIN_SO_PATH="$(pwd)/slang.so"

if [ ! -f "$PLUGIN_SO_PATH" ]; then
    error "Slang plugin build failed: $PLUGIN_SO_PATH not found."
fi

mkdir -p "$YOSYS_PLUGINS_DIR"
cp "$PLUGIN_SO_PATH" "$YOSYS_PLUGINS_DIR/"

# ---- Step 4: Confirm installation and usage ----
echo
success "Yosys installed at: $(which yosys 2>/dev/null || echo "$YOSYS_PREFIX/bin/yosys")"
success "Slang plugin installed at: $YOSYS_PLUGINS_DIR/$(basename "$PLUGIN_SO_PATH")"
echo

info "Attempting to confirm Slang plugin functionality within this script..."
if command -v yosys &> /dev/null; then
    # Create a dummy empty SystemVerilog file
    DUMMY_SV_FILE="$(mktemp /tmp/dummy_sv_XXXXXX.sv)"
    echo "" > "$DUMMY_SV_FILE" # Empty file is enough for frontend to not error on 'no input files'

    # Try to load the slang plugin and then read the dummy file using read_slang.
    # We'll rely on the exit code of Yosys and the presence of "Executing SLANG frontend."
    # We remove the 'exit' command from the Yosys script as it was causing issues
    # with the automatic pass execution. We'll simply let Yosys finish its default flow.
    YOSYS_CHECK_OUTPUT=$(yosys -Q -p "plugin -i slang; read_slang $DUMMY_SV_FILE" 2>&1 || true)
    # The '|| true' prevents set -e from exiting the script if yosys returns a non-zero.
    # We'll check the output and then the actual exit code in the if/else.

    if echo "$YOSYS_CHECK_OUTPUT" | grep -q "Executing SLANG frontend." && \
       echo "$YOSYS_CHECK_OUTPUT" | grep -q "Build succeeded: 0 errors"; then
        success "Slang plugin successfully loaded and recognized by Yosys for SystemVerilog!"
    else
        warn "Slang plugin might not be fully recognized by Yosys. Manual check recommended."
        info "Yosys output during check:"
        echo "$YOSYS_CHECK_OUTPUT"
    fi
    rm "$DUMMY_SV_FILE" # Clean up the dummy file
else
    warn "Yosys command not found in PATH even after adding. Check installation."
fi
echo
info 'For permanent use, add this to your shell config (e.g., ~/.bashrc or ~/.zshrc):'
info "  export PATH=\"$YOSYS_PREFIX/bin:\\\$PATH\""
info "Then, run 'source ~/.bashrc' (or your respective shell config) or restart your terminal."
echo
info "You can then run Yosys with SystemVerilog support using:"
info "  yosys -m slang <your_systemverilog_file.sv>"
