#!/usr/bin/env bash
# Start backend + cloudflared quick tunnel for the Gloss demo.
#
#   ./scripts/demo-up.sh
#
# Updates the Cloudflare Worker secret BACKEND_URL when the tunnel URL changes
# (no git push or frontend redeploy). One-time setup: cd frontend && npm run build
# && npx wrangler deploy  (after pulling this worker-proxy change).

set -uo pipefail
cd "$(dirname "$0")/.."

API_URL="http://localhost:8000"
LOG_DIR="${TMPDIR:-/tmp}/gloss-demo"
TUNNEL_LOG="$LOG_DIR/cloudflared.log"
CONFIG_FILE="frontend/public/config.json"
mkdir -p "$LOG_DIR"

log() { printf '\033[36m[demo]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[demo]\033[0m %s\n' "$*"; }

for bin in docker cloudflared; do
  command -v "$bin" >/dev/null || { warn "$bin not found."; exit 1; }
done

log "Starting containers…"
docker compose up -d db redis api worker || { warn "docker compose failed"; exit 1; }

for _ in $(seq 1 60); do
  curl -fsS "$API_URL/health" >/dev/null 2>&1 && break
  sleep 2
done
curl -fsS "$API_URL/health" >/dev/null 2>&1 || { warn "API not healthy"; exit 1; }

write_config() {
  local url="$1"
  printf '{\n  "apiUrl": "%s"\n}\n' "$url" >"$CONFIG_FILE"
}

LAST_BACKEND_URL_FILE="$LOG_DIR/last-backend-url"

sync_config_to_github() {
  if git diff --quiet "$CONFIG_FILE" 2>/dev/null; then
    return 0
  fi
  log "Pushing config.json to GitHub (Cloudflare redeploys in ~2 min)…"
  git add "$CONFIG_FILE"
  git commit -m "Update tunnel URL" || return 1
  if git push origin main; then
    log "Pushed. Hard-refresh gloss.priyansha016.workers.dev in ~2 min."
  else
    warn "Push failed. Run: git add $CONFIG_FILE && git commit -m 'Update tunnel URL' && git push"
  fi
}

sync_backend_secret() {
  local url="$1"
  if [ -f "$LAST_BACKEND_URL_FILE" ] && [ "$(cat "$LAST_BACKEND_URL_FILE")" = "$url" ]; then
    return 0
  fi
  printf '%s' "$url" >"$LAST_BACKEND_URL_FILE"
  if [ ! -d frontend/node_modules ]; then
    return 0
  fi
  log "Optional: updating Cloudflare BACKEND_URL secret…"
  if printf '%s' "$url" | (cd frontend && npx wrangler secret put BACKEND_URL 2>/dev/null); then
    log "BACKEND_URL secret set."
  fi
}

TUNNEL_PID=""
start_tunnel() {
  : >"$TUNNEL_LOG"
  cloudflared tunnel --url "$API_URL" --no-autoupdate >>"$TUNNEL_LOG" 2>&1 &
  TUNNEL_PID=$!
  for _ in $(seq 1 30); do
    local url
    url=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" | head -1)
    if [ -n "$url" ]; then
      printf '\n\033[32m[demo] Public API: %s\033[0m\n' "$url"
      write_config "$url"
      sync_config_to_github || true
      sync_backend_secret "$url" || true
      return 0
    fi
    sleep 1
  done
  warn "Tunnel started but no URL in log"
}

cleanup() {
  log "Stopping tunnel (containers keep running)."
  [ -n "$TUNNEL_PID" ] && kill "$TUNNEL_PID" 2>/dev/null
  exit 0
}
trap cleanup INT TERM

caffeinate -dimsu -w $$ &
start_tunnel
log "Watching tunnel. Keep this terminal open."

while true; do
  sleep 30
  if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
    warn "Tunnel died — restarting (BACKEND_URL will update automatically)."
    start_tunnel
  fi
done
