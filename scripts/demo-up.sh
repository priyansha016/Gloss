#!/usr/bin/env bash
# Start backend + cloudflared quick tunnel. Updates frontend/public/config.json
# with the new tunnel URL so the live site can reach your Mac API.
#
#   ./scripts/demo-up.sh
#
# After it prints the URL, commit and push config.json if it changed:
#   git add frontend/public/config.json && git commit -m "Update tunnel URL" && git push

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
  log "Wrote $CONFIG_FILE"
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
      printf '\033[33m[demo] git add %s && git commit -m "Update tunnel URL" && git push\033[0m\n\n' "$CONFIG_FILE"
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
    warn "Tunnel died — restarting (URL will change; push config.json again)."
    start_tunnel
  fi
done
