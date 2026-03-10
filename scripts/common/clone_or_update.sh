#!/usr/bin/env bash

set -Eeuo pipefail

# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/logger.sh"

clone_or_update() {
    local repo_url="$1"
    local target_dir="$2"
    local recursive="${3:-false}"

    export GIT_TERMINAL_PROMPT=0

    if [[ -d "${target_dir}/.git" ]]; then
        info "Updating existing repository: ${target_dir}"
        pushd "${target_dir}" >/dev/null

        # Sanity check: verify this is a real git repo with the expected remote.
        if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
            warning "${target_dir} is not a healthy git work tree. Re-cloning."
            popd >/dev/null
            rm -rf "${target_dir}"
            clone_or_update "${repo_url}" "${target_dir}" "${recursive}"
            return
        fi

        local origin_url=""
        origin_url="$(git remote get-url origin 2>/dev/null || true)"

        if [[ -z "${origin_url}" ]]; then
            warning "Repository ${target_dir} has no origin remote. Re-cloning."
            popd >/dev/null
            rm -rf "${target_dir}"
            clone_or_update "${repo_url}" "${target_dir}" "${recursive}"
            return
        fi

        if [[ "${origin_url}" != "${repo_url}" ]]; then
            warning "Repository ${target_dir} points to ${origin_url}, expected ${repo_url}. Re-cloning."
            popd >/dev/null
            rm -rf "${target_dir}"
            clone_or_update "${repo_url}" "${target_dir}" "${recursive}"
            return
        fi

        # Clean stale lock files from interrupted earlier runs.
        find . -path '*/.git/index.lock' -delete 2>/dev/null || true
        find . -path '*/.git/modules/*/index.lock' -delete 2>/dev/null || true

        git fetch --all --prune --tags

        local branch=""
        branch="$(git symbolic-ref --short HEAD 2>/dev/null || echo "DETACHED")"

        if [[ "${branch}" != "DETACHED" ]]; then
            if git show-ref --verify --quiet "refs/remotes/origin/${branch}"; then
                info "Resetting ${branch} to origin/${branch}"
                git reset --hard "origin/${branch}"
            else
                warning "origin/${branch} not found; skipping hard reset"
            fi
        else
            warning "Detached HEAD detected; skipping hard reset"
        fi

        if [[ "${recursive}" == "true" ]]; then
            info "Synchronizing submodules"
            git submodule sync --recursive
            git submodule update --init --recursive --force
        fi

        popd >/dev/null
        return
    fi

    if [[ -e "${target_dir}" ]]; then
        warning "Directory ${target_dir} exists but is not a git repo. Removing it."
        rm -rf "${target_dir}"
    fi

    info "Cloning repository: ${repo_url} -> ${target_dir}"
    if [[ "${recursive}" == "true" ]]; then
        git clone --recurse-submodules "${repo_url}" "${target_dir}"
    else
        git clone "${repo_url}" "${target_dir}"
    fi
}