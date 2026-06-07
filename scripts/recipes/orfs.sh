#!/usr/bin/env bash

set -Eeuo pipefail

# shellcheck source=/dev/null
source "$(dirname "$0")/../common/logger.sh"
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/paths.sh"
# shellcheck source=/dev/null
source "$(dirname "$0")/../common/check_deps.sh"

ORFS_REPOSITORY="https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts.git"
# SaxoFlow releases may override this pin after compatibility qualification.
ORFS_REVISION="${SAXOFLOW_ORFS_REVISION:-eb14d768b6c34cf4f8c5177f3531422b94cf2544}"
EXPECTED_OPENROAD_REVISION="49bd051a10f0dd5bb89eba9acf668e8362b883d8"
DATA_ROOT="${SAXOFLOW_DATA_HOME:-$HOME/.local/share/saxoflow}"
ORFS_ROOT="$DATA_ROOT/orfs"
INSTALL_ROOT="$ORFS_ROOT/$ORFS_REVISION"
TEMP_ROOT="$ORFS_ROOT/.install-$ORFS_REVISION"
LOCAL_BIN="$HOME/.local/bin"
MIN_FREE_KB=$((2 * 1024 * 1024))

info "Installing OpenROAD Flow Scripts revision $ORFS_REVISION"
info "License: BSD-3-Clause and component-specific upstream licenses"
info "Source: $ORFS_REPOSITORY"
info "Estimated transfer: 500 MB; required free disk space: 2 GB"
check_deps git make python3 ca-certificates

OPENROAD_BIN="$(command -v openroad 2>/dev/null || true)"
if [[ -z "$OPENROAD_BIN" && -x "$HOME/.local/openroad/bin/openroad" ]]; then
    OPENROAD_BIN="$HOME/.local/openroad/bin/openroad"
fi
if [[ -z "$OPENROAD_BIN" ]]; then
    fatal "OpenROAD is required. Run 'saxoflow install openroad' first."
fi

mkdir -p "$ORFS_ROOT" "$LOCAL_BIN"
AVAILABLE_KB="$(df -Pk "$ORFS_ROOT" | awk 'NR == 2 {print $4}')"
if [[ ! "$AVAILABLE_KB" =~ ^[0-9]+$ || "$AVAILABLE_KB" -lt "$MIN_FREE_KB" ]]; then
    fatal "At least 2 GB of free disk space is required under $ORFS_ROOT."
fi

if [[ ! -d "$INSTALL_ROOT/.git" ]]; then
    if [[ -e "$TEMP_ROOT" && ! -d "$TEMP_ROOT/.git" ]]; then
        FAILED_ROOT="$TEMP_ROOT.failed.$(date +%Y%m%d%H%M%S)"
        warning "Preserving invalid partial install at $FAILED_ROOT"
        mv "$TEMP_ROOT" "$FAILED_ROOT"
    fi
    if [[ ! -d "$TEMP_ROOT/.git" ]]; then
        info "Cloning ORFS without installing another OpenROAD binary"
        git clone --filter=blob:none --no-checkout "$ORFS_REPOSITORY" "$TEMP_ROOT"
    else
        info "Resuming the partial ORFS checkout at $TEMP_ROOT"
    fi
    git -C "$TEMP_ROOT" fetch --depth 1 origin "$ORFS_REVISION"
    git -C "$TEMP_ROOT" sparse-checkout init --no-cone
    cat > "$TEMP_ROOT/.git/info/sparse-checkout" <<'EOF'
/*
!/flow/platforms/*/
EOF
    git -C "$TEMP_ROOT" checkout --detach FETCH_HEAD

    test -f "$TEMP_ROOT/flow/Makefile" || fatal "ORFS flow Makefile is missing"
    ACTUAL_REVISION="$(git -C "$TEMP_ROOT" rev-parse HEAD)"
    [[ "$ACTUAL_REVISION" == "$ORFS_REVISION" ]] || \
        fatal "ORFS revision verification failed: expected $ORFS_REVISION, got $ACTUAL_REVISION"
    ACTUAL_OPENROAD_REVISION="$(
        git -C "$TEMP_ROOT" ls-tree HEAD tools/OpenROAD | awk '{print $3}'
    )"
    [[ "$ACTUAL_OPENROAD_REVISION" == "$EXPECTED_OPENROAD_REVISION" ]] || \
        fatal "ORFS OpenROAD revision verification failed"
    MAKEFILE_SHA256="$(sha256sum "$TEMP_ROOT/flow/Makefile" | awk '{print $1}')"
    printf '%s\n' "$ORFS_REVISION" > "$TEMP_ROOT/.saxoflow-revision"
    cat > "$TEMP_ROOT/.saxoflow-install.json" <<EOF
{
  "schema_version": 1,
  "repository": "$ORFS_REPOSITORY",
  "revision": "$ORFS_REVISION",
  "openroad_revision": "$ACTUAL_OPENROAD_REVISION",
  "flow_makefile_sha256": "$MAKEFILE_SHA256"
}
EOF
    mv "$TEMP_ROOT" "$INSTALL_ROOT"
else
    info "Pinned ORFS revision is already installed"
fi

ln -sfn "$INSTALL_ROOT" "$ORFS_ROOT/current"
printf '%s\n' "$ORFS_REVISION" > "$ORFS_ROOT/CURRENT"

cat > "$LOCAL_BIN/orfs" <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
exec make -C "$INSTALL_ROOT/flow" OPENROAD_EXE="$OPENROAD_BIN" "\$@"
EOF
chmod +x "$LOCAL_BIN/orfs"

OPENROAD_VERSION="$("$OPENROAD_BIN" -version 2>/dev/null || true)"
info "Reusing OpenROAD: $OPENROAD_BIN"
info "OpenROAD version: ${OPENROAD_VERSION:-unknown}"
success "ORFS installed at $INSTALL_ROOT"
info "Activate PDK platforms with: saxoflow pdk install <platform> --accept-license"
