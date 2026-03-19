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

info "Installing Kactus2 IP-XACT toolset..."

USER_PREFIX="$INSTALL_DIR/kactus2"
BIN_DIR_MANAGED="$USER_PREFIX/bin"
KACTUS2_VERSION="${KACTUS2_VERSION:-3.14.0}"
SRC_URL="https://sourceforge.net/projects/kactus2/files/kactus2-${KACTUS2_VERSION}.tar.gz/download"

check_deps \
  curl \
  tar \
  make \
  g++ \
  qt6-base-dev \
  qt6-tools-dev \
  qt6-tools-dev-tools \
  qt6-documentation-tools \
  libqt6svg6-dev \
  python3-dev \
  swig \
  libgl-dev

# Resolve Qt qmake toolchain details after dependencies are present.
QMAKE_BIN=""
for candidate in "$(command -v qmake6 2>/dev/null || true)" "/usr/lib/qt6/bin/qmake" "$(command -v qmake 2>/dev/null || true)"; do
  if [[ -n "$candidate" && -x "$candidate" ]]; then
    QMAKE_BIN="$candidate"
    break
  fi
done

if [[ -z "$QMAKE_BIN" ]]; then
  fatal "Qt qmake was not found after dependency installation"
fi

QTBIN_PATH="$("$QMAKE_BIN" -query QT_INSTALL_BINS 2>/dev/null || true)"
if [[ -z "$QTBIN_PATH" ]]; then
  QTBIN_PATH="$(dirname "$QMAKE_BIN")"
fi
QTBIN_PATH="${QTBIN_PATH%/}/"

PYTHON_CONFIG_BIN="$(command -v python3-config || true)"
if [[ -z "$PYTHON_CONFIG_BIN" ]]; then
  fatal "python3-config was not found; install python3-dev"
fi

rm -rf "$USER_PREFIX"
mkdir -p "$USER_PREFIX" "$BIN_DIR_MANAGED"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

SRC_TARBALL="$TMP_DIR/kactus2.tar.gz"
SRC_DIR="$TMP_DIR/src"
mkdir -p "$SRC_DIR"

info "Downloading: $SRC_URL"
curl -fL "$SRC_URL" -o "$SRC_TARBALL"

tar -xzf "$SRC_TARBALL" -C "$SRC_DIR"

# SourceForge release tarball extracts directly under source root.
if [[ -f "$SRC_DIR/configure" ]]; then
  KACTUS_SRC="$SRC_DIR"
else
  KACTUS_SRC="$(find "$SRC_DIR" -maxdepth 2 -type f -name configure -printf '%h\n' | head -n1 || true)"
fi

if [[ -z "$KACTUS_SRC" || ! -f "$KACTUS_SRC/configure" ]]; then
  fatal "Could not locate Kactus2 source root after extraction"
fi

pushd "$KACTUS_SRC" >/dev/null

# Configure scripts expect these paths in-place.
sed -i "s|^QTBIN_PATH=.*|QTBIN_PATH=\"$QTBIN_PATH\"|" configure
sed -i "s|^PYTHON_CONFIG=.*|PYTHON_CONFIG=${PYTHON_CONFIG_BIN##*/}|" .qmake.conf
sed -i "s|^LOCAL_INSTALL_DIR=.*|LOCAL_INSTALL_DIR=\"$USER_PREFIX\"|" .qmake.conf

# Upstream 3.14.x release tarball needs this signature alignment on some
# modern toolchains to avoid QStringList/QVector mismatch during build.
python3 - <<'PY'
from pathlib import Path
files = [
    Path('IPXACTmodels/common/validators/QualifierValidator.h'),
    Path('IPXACTmodels/common/validators/QualifierValidator.cpp'),
]
for p in files:
    s = p.read_text(encoding='utf-8')
    s = s.replace('QVector<QString>& errorList', 'QStringList& errorList')
    p.write_text(s, encoding='utf-8')
PY

./configure
make -j"$(nproc)"
make install

popd >/dev/null

# Locate installed executable and create a managed launcher script.
KACTUS_BIN=""
for candidate in \
  "$USER_PREFIX/kactus2" \
  "$USER_PREFIX/usr/bin/kactus2" \
  "$(find "$USER_PREFIX" -maxdepth 4 -type f -name kactus2 -perm -111 2>/dev/null | head -n1 || true)"; do
  if [[ -n "$candidate" && -x "$candidate" ]]; then
    KACTUS_BIN="$candidate"
    break
  fi
done

if [[ -z "$KACTUS_BIN" ]]; then
  fatal "kactus2 binary was not found after build/install"
fi

cat > "$BIN_DIR_MANAGED/kactus2" <<EOF
#!/usr/bin/env bash
set -e
export LD_LIBRARY_PATH="$USER_PREFIX:$USER_PREFIX/lib:$USER_PREFIX/lib64:\${LD_LIBRARY_PATH:-}"
exec "$KACTUS_BIN" "\$@"
EOF
chmod +x "$BIN_DIR_MANAGED/kactus2"

chown -R "$(id -u):$(id -g)" "$USER_PREFIX" || true
persist_path_entry "$BIN_DIR_MANAGED" "Added by SaxoFlow Kactus2 installer"

if "$BIN_DIR_MANAGED/kactus2" --version >/dev/null 2>&1; then
  success "Kactus2 installed successfully to $BIN_DIR_MANAGED"
  info "Detected version: $("$BIN_DIR_MANAGED/kactus2" --version 2>&1 | head -n1)"
else
  fatal "kactus2 binary was not executable after installation"
fi
