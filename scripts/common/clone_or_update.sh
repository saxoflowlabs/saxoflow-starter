#!/usr/bin/env bash

# saxoflow/scripts/common/clone_or_update.sh — Professional Git repo manager

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/logger.sh"

clone_or_update() {
    local repo_url=$1
    local target_dir=$2
    local recursive="${3:-false}"

    export GIT_TERMINAL_PROMPT=0  # Prevent interactive auth prompts

    # If repo already exists
    if [[ -d "$target_dir/.git" ]]; then
        info "🔄 Updating existing repository: $target_dir"
        pushd "$target_dir" >/dev/null

        # First, verify repo health before proceeding
        if ! git remote -v >/dev/null 2>&1; then
            error "❌ $target_dir appears corrupted. Deleting and recloning."
            popd >/dev/null
            rm -rf "$target_dir"
            clone_or_update "$repo_url" "$target_dir" "$recursive"
            return
        fi

        # Update repository
        git fetch --all --prune

        # Detect branch vs detached HEAD
        local branch
        branch=$(git symbolic-ref --short HEAD 2>/dev/null || echo "DETACHED")

        if [[ "$branch" != "DETACHED" ]]; then
            info "🔄 Resetting branch '$branch' to origin/$branch"
            git reset --hard "origin/$branch"
        else
            warn "⚠ Detached HEAD detected; not resetting branch."
        fi

        if [[ "$recursive" == "true" ]]; then
            info "🔄 Updating submodules..."
            git submodule update --init --recursive
        fi

        popd >/dev/null

    else
        if [[ -e "$target_dir" ]]; then
            warn "⚠ Directory '$target_dir' exists but not a Git repo. Removing."
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
