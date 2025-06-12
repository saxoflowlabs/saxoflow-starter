#!/bin/bash

# Universal safe clone-or-update function for SaxoFlow installers

set -euo pipefail

clone_or_update() {
    local repo_url="$1"
    local target_dir="$2"

    if [ -d "$target_dir/.git" ]; then
        echo "🔄 Updating existing repo: $target_dir"
        (
            cd "$target_dir"
            git pull --ff-only || echo "⚠️ Warning: Could not fast-forward $target_dir. Manual review may be needed."
        )
    elif [ -d "$target_dir" ]; then
        echo "⚠️ Directory $target_dir exists but is not a Git repo. Skipping clone."
    else
        echo "📦 Cloning repository: $repo_url → $target_dir"
        git clone "$repo_url" "$target_dir"
    fi
}
