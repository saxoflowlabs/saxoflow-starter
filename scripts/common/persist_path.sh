#!/usr/bin/env bash

# shellcheck shell=bash

if [[ "${SAXOFLOW_PERSIST_PATH_INITIALIZED:-0}" == "1" ]]; then
  return 0
fi
export SAXOFLOW_PERSIST_PATH_INITIALIZED=1

_persist_path_log() {
  local level="$1"
  local message="$2"

  case "$level" in
    success)
      if declare -F success >/dev/null 2>&1; then
        success "$message"
      else
        printf 'SUCCESS: %s\n' "$message"
      fi
      ;;
    info)
      if declare -F info >/dev/null 2>&1; then
        info "$message"
      else
        printf 'INFO: %s\n' "$message"
      fi
      ;;
    warn)
      if declare -F warning >/dev/null 2>&1; then
        warning "$message"
      elif declare -F warn >/dev/null 2>&1; then
        warn "$message"
      else
        printf 'WARNING: %s\n' "$message"
      fi
      ;;
  esac
}

_persist_path_shell_rc() {
  local shell_name

  if [[ -n "${SHELL:-}" ]]; then
    shell_name="$(basename "$SHELL")"
  else
    shell_name="bash"
  fi

  case "$shell_name" in
    zsh)
      printf '%s\n' "$HOME/.zshrc"
      ;;
    fish)
      printf '%s\n' "$HOME/.config/fish/config.fish"
      ;;
    *)
      printf '%s\n' "$HOME/.bashrc"
      ;;
  esac
}

persist_path_entry() {
  local path_entry="$1"
  local comment="${2:-Added by SaxoFlow installer}"
  local shell_rc shell_name export_line

  if [[ -z "$path_entry" ]]; then
    _persist_path_log warn "persist_path_entry called with an empty path."
    return 1
  fi

  shell_rc="$(_persist_path_shell_rc)"
  shell_name="$(basename "${SHELL:-bash}")"
  mkdir -p "$(dirname "$shell_rc")"
  touch "$shell_rc"

  case "$shell_name" in
    fish)
      export_line="fish_add_path \"$path_entry\""
      ;;
    *)
      export_line="export PATH=\"$path_entry:\$PATH\""
      ;;
  esac

  if grep -qF "$path_entry" "$shell_rc" 2>/dev/null; then
    _persist_path_log info "PATH entry already present in $shell_rc -- skipping $path_entry"
    return 0
  fi

  {
    printf '\n'
    printf '# %s\n' "$comment"
    printf '%s\n' "$export_line"
  } >> "$shell_rc"

  _persist_path_log success "Added $path_entry to PATH via $shell_rc"
}