#!/bin/bash

set -e
source "$(dirname "$0")/logger.sh"

# clone_or_update <url> <target_dir> [recursive]
clone_or_update() {
    local url=$1
    local target_dir=$2
    local recursive=${3:-false}  # <-- 🩺 THE FIX

    if [ ! -d "$target_dir" ]; then
        info "📦 Cloning repository: $url → $target_dir"
        if [ "$recursive" = "true" ]; then
            GIT_TERMINAL_PROMPT=0 git clone --recursive "$url" "$target_dir"
        else
            GIT_TERMINAL_PROMPT=0 git clone "$url" "$target_dir"
        fi
    else
        info "🔄 Updating existing repo: $target_dir"
        cd "$target_dir"
        GIT_TERMINAL_PROMPT=0 git pull || true
        cd - >/dev/null
    fi
}
