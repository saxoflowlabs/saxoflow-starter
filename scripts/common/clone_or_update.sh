#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/logger.sh"

clone_or_update() {
    local repo_url=$1
    local target_dir=$2
    local recursive="${3:-false}"
    export GIT_TERMINAL_PROMPT=0

    if [[ -d "$target_dir/.git" ]]; then
        info "🔄 Updating existing repo: $target_dir"
        pushd "$target_dir" >/dev/null

        git fetch --all --prune

        # Only reset if we're on a branch (not a tag / detached HEAD)
        local branch
        branch=$(git rev-parse --abbrev-ref HEAD || echo "HEAD")
        if [[ "$branch" != "HEAD" && -n "$branch" ]]; then
            info "🔄 Resetting branch '$branch' to origin/$branch"
            git reset --hard "origin/$branch"
        else
            warn "⚠ Detached HEAD or tag detected; skipping reset"
        fi

        if [[ "$recursive" == "true" ]]; then
            git submodule update --init --recursive
        fi

        popd >/dev/null
    else
        if [[ -e "$target_dir" ]]; then
            warn "⚠ $target_dir exists but is not a Git repo; removing."
            rm -rf "$target_dir"
        fi
        info "📦 Cloning repository: $repo_url → $target_dir"
        if [[ "$recursive" == "true" ]]; then
            git clone --recurse-submodules "$repo_url" "$target_dir"
        else
            git clone "$repo_url" "$target_dir"
        fi
    fi
}
