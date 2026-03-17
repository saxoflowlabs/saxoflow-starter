#!/usr/bin/env bash

set -Eeuo pipefail

# shellcheck source=/dev/null
source "$(dirname "$0")/../common/logger.sh"
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/paths.sh"
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/persist_path.sh"
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/check_deps.sh"
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/clone_or_update.sh"

INSTALL_ROOT="${INSTALL_DIR}/openroad"
BIN_DIR="${INSTALL_ROOT}/bin"
OPENROAD_SRC_DIR="${TOOLS_DIR}/openroad"
LOCAL_BIN_DIR="${INSTALL_DIR}/bin"
BAZELISK_BIN="${LOCAL_BIN_DIR}/bazelisk"
BAZEL_BIN="${LOCAL_BIN_DIR}/bazel"
LOCAL_OPENROAD_LINK="${LOCAL_BIN_DIR}/openroad"

info "Installing OpenROAD (Bazelisk method)"

mkdir -p "${TOOLS_DIR}" "${LOCAL_BIN_DIR}"
cd "${TOOLS_DIR}"

check_deps \
  build-essential cmake gcc g++ git curl unzip zip \
  python3 python3-pip default-jdk \
  libx11-dev libgl1-mesa-dev libxrender-dev libxrandr-dev \
  libxcursor-dev libxi-dev zlib1g-dev \
  libxcb-cursor0 libx11-xcb1 libxcb1 libxcb-render0 libxcb-render-util0 \
  libxcb-shape0 libxcb-randr0 libxcb-xfixes0 libxcb-xkb1 libxcb-sync1 \
  libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-util1 \
  libxkbcommon0 libxkbcommon-x11-0 libfontconfig1

clone_or_update "https://github.com/The-OpenROAD-Project/OpenROAD.git" "openroad" "true"
cd "${OPENROAD_SRC_DIR}"

# Clean repo-local build artifacts only.
rm -rf build bazel-* .cache

# Install Bazelisk under its real name.
if [[ ! -x "${BAZELISK_BIN}" ]]; then
    info "Installing Bazelisk"
    curl -fL \
      "https://github.com/bazelbuild/bazelisk/releases/latest/download/bazelisk-linux-amd64" \
      -o "${BAZELISK_BIN}"
    chmod +x "${BAZELISK_BIN}"
fi

# Also provide `bazel` for tools/scripts that invoke that name.
ln -sf "${BAZELISK_BIN}" "${BAZEL_BIN}"

# Make sure this script can resolve both names.
export PATH="${LOCAL_BIN_DIR}:${PATH}"
hash -r

command -v bazelisk >/dev/null 2>&1 || fatal "bazelisk not found in PATH after installation"
command -v bazel >/dev/null 2>&1 || fatal "bazel not found in PATH after installation"

export LANG=C.UTF-8
export LC_ALL=C.UTF-8

rm -rf "${INSTALL_ROOT}"
mkdir -p "${INSTALL_ROOT}" "${BIN_DIR}"

# Bazel install places the real binary directly in INSTALL_ROOT.
bazelisk run --config=release --//:platform=gui //:install -- "${INSTALL_ROOT}"

chown -R "$(id -u):$(id -g)" "${INSTALL_ROOT}" || true

# Create a stable wrapper under INSTALL_ROOT/bin/openroad.
if [[ -x "${INSTALL_ROOT}/openroad" ]]; then
    cat > "${BIN_DIR}/openroad" <<EOF
#!/usr/bin/env bash
exec "${INSTALL_ROOT}/openroad" "\$@"
EOF
    chmod +x "${BIN_DIR}/openroad"
elif [[ ! -x "${BIN_DIR}/openroad" ]]; then
    fatal "Install completed but openroad binary not found at ${INSTALL_ROOT}/openroad or ${BIN_DIR}/openroad"
fi

# Expose OpenROAD through ~/.local/bin/openroad so normal PATH lookup works.
ln -sf "${BIN_DIR}/openroad" "${LOCAL_OPENROAD_LINK}"
hash -r || true

# Final verification.
if [[ ! -x "${LOCAL_OPENROAD_LINK}" ]]; then
    fatal "OpenROAD launcher was not created at ${LOCAL_OPENROAD_LINK}"
fi

OPENROAD_VERSION="$("${LOCAL_OPENROAD_LINK}" -version 2>/dev/null || true)"
if [[ -z "${OPENROAD_VERSION}" ]]; then
    warning "OpenROAD installed, but version probe returned no output. Try: ${LOCAL_OPENROAD_LINK} -version"
else
    info "Detected OpenROAD version: ${OPENROAD_VERSION}"
fi

persist_path_entry "${LOCAL_BIN_DIR}" "Added by SaxoFlow openroad installer"

info "OpenROAD installed successfully at ${BIN_DIR}/openroad"
info "OpenROAD exposed on PATH via ${LOCAL_OPENROAD_LINK}"