#!/usr/bin/env bash
set -euo pipefail

SEARXNG_CONTAINER_NAME="searxng"
SEARXNG_IMAGE="docker.io/searxng/searxng:latest"
SEARXNG_PORT="8080"
SEARXNG_BASE_URL="http://127.0.0.1:${SEARXNG_PORT}"
SEARXNG_CONFIG_DIR="${HOME}/.config/searxng"
SEARXNG_SETTINGS_FILE="${SEARXNG_CONFIG_DIR}/settings.yml"
BASHRC_FILE="${HOME}/.bashrc"

log() {
  printf "[setup-web] %s\n" "$*"
}

ensure_line_in_file() {
  local file="$1"
  local line="$2"
  touch "$file"
  if ! grep -Fqx "$line" "$file"; then
    printf "%s\n" "$line" >> "$file"
  fi
}

ensure_runtime() {
  if command -v docker >/dev/null 2>&1; then
    log "Container runtime detected: $(docker --version | head -n 1)"
    return
  fi

  log "docker command not found; installing podman-docker (requires sudo)."
  sudo apt update
  sudo apt install -y podman-docker
  log "Installed podman-docker."
}

write_searxng_settings() {
  mkdir -p "$SEARXNG_CONFIG_DIR"

  if [[ ! -f "$SEARXNG_SETTINGS_FILE" ]]; then
    local secret_key
    secret_key="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(24))
PY
)"

    cat > "$SEARXNG_SETTINGS_FILE" <<EOF
use_default_settings: true

server:
  secret_key: "${secret_key}"

search:
  formats:
    - html
    - json
EOF
    log "Created SearXNG settings at ${SEARXNG_SETTINGS_FILE}."
  else
    if ! grep -Eq '^search:' "$SEARXNG_SETTINGS_FILE"; then
      cat >> "$SEARXNG_SETTINGS_FILE" <<'EOF'

search:
  formats:
    - html
    - json
EOF
      log "Updated existing SearXNG settings with JSON format support."
    fi
  fi
}

start_container() {
  docker rm -f "$SEARXNG_CONTAINER_NAME" >/dev/null 2>&1 || true

  docker run -d \
    --name "$SEARXNG_CONTAINER_NAME" \
    --restart=always \
    -p "${SEARXNG_PORT}:8080" \
    -v "${SEARXNG_SETTINGS_FILE}:/etc/searxng/settings.yml" \
    "$SEARXNG_IMAGE" >/dev/null

  log "Started ${SEARXNG_CONTAINER_NAME} on ${SEARXNG_BASE_URL}."
}

wait_for_health() {
  local tries=20
  local ok=0

  for _ in $(seq 1 "$tries"); do
    if curl -fsS "${SEARXNG_BASE_URL}/search?q=openroad&format=json" >/dev/null 2>&1; then
      ok=1
      break
    fi
    sleep 1
  done

  if [[ "$ok" -ne 1 ]]; then
    log "SearXNG did not become ready in time. Recent logs:"
    docker logs --tail 80 "$SEARXNG_CONTAINER_NAME" || true
    exit 1
  fi

  log "SearXNG JSON endpoint is healthy."
}

persist_env() {
  ensure_line_in_file "$BASHRC_FILE" "export WEB_RESEARCH_PROVIDER=searxng"
  ensure_line_in_file "$BASHRC_FILE" "export SEARXNG_BASE_URL=${SEARXNG_BASE_URL}"
  ensure_line_in_file "$BASHRC_FILE" "unset SEARXNG_FALLBACK_URLS"

  export WEB_RESEARCH_PROVIDER=searxng
  export SEARXNG_BASE_URL="$SEARXNG_BASE_URL"
  unset SEARXNG_FALLBACK_URLS

  log "Persisted shell configuration in ${BASHRC_FILE}."
}

main() {
  ensure_runtime
  write_searxng_settings
  start_container
  wait_for_health
  persist_env

  log "Done. Open a new shell or run: source ${BASHRC_FILE}"
  log "Then run SaxoFlow research with web.search normally."
}

main "$@"
