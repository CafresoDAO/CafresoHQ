#!/usr/bin/env bash
# local_hq.sh — your own office on this machine, reachable from the Cafreso
# sign-in at https://ai.cafreso.com. docs/LOCAL_HQ.md.
#
# The shell at ai.cafreso.com looks for a "Local machine" office on
# http://localhost:8787 (then 8788) the moment you open HQ; serve.py listens
# on 8787 by default. This script keeps that office up as a per-user
# LaunchAgent (starts at login, restarts if it dies) — nothing system-wide,
# no admin password, and `uninstall` removes every trace.
#
#   scripts/local_hq.sh install      # write the LaunchAgent, start it, probe /health
#   scripts/local_hq.sh status       # is it up? what does it answer?
#   scripts/local_hq.sh restart      # after a `git pull` (rebuilds the UI first)
#   scripts/local_hq.sh logs         # tail the office's log
#   scripts/local_hq.sh uninstall    # stop it and remove the LaunchAgent
#   scripts/local_hq.sh run          # foreground, no LaunchAgent (for a look)
#
# Env: PORT (default 8787), CAFRESOHQ_HQ_STATE_DIR (default <repo>/hq-state),
#      CAFRESOHQ_PYTHON (default: the python3 on PATH).
# If `mkcert` is on PATH, serve.py issues a browser-trusted localhost cert on
# its own and the office also answers https://localhost:8787 (Safari needs
# that; Chrome, Brave and Edge accept plain http://localhost from a secure
# page). Installing mkcert's CA is a one-time step YOU run: `brew install
# mkcert && mkcert -install`.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.cafreso.hq"
PORT="${PORT:-8787}"
STATE_DIR="${CAFRESOHQ_HQ_STATE_DIR:-$ROOT/hq-state}"
PY="${CAFRESOHQ_PYTHON:-$(command -v python3 || true)}"
AGENTS_DIR="${LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}"
PLIST="$AGENTS_DIR/$LABEL.plist"
LOG_DIR="${CAFRESOHQ_LOG_DIR:-$HOME/Library/Logs}"
LOG="$LOG_DIR/cafreso-hq.log"
DOMAIN="gui/$(id -u)"

usage() { sed -n '2,26p' "$0"; }

# 127.0.0.1 on purpose: `localhost` resolves to ::1 first, and on a Mac where
# Docker Desktop forwards the same port for a container, the IPv6 side is
# Docker's and answers nothing — measured here with the search worker on
# 8787/8788. The office binds IPv4 loopback; a browser falls back to it too.
# The body must be ours ("status": "ok" from serve.py), not just any 200.
health() {
  local b
  b="$(curl -s -m 4 "http://127.0.0.1:$PORT/health" 2>/dev/null)" || return 1
  case "$b" in *'"status": "ok"'*) printf '%s' "$b" ;; *) return 1 ;; esac
}

port_in_use_by_other() {
  # something else already listening here (Docker's forward, another app)
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | awk 'NR>1 {print $1}' | grep -vqi python
}

connect_hint() {
  echo "Next: sign in at https://ai.cafreso.com → HQ → 💻 Local machine."
  if [ "$PORT" = 8787 ] || [ "$PORT" = 8788 ]; then
    echo "      It finds the office on its own → Connect."
  else
    echo "      Type  $PORT  in the \"custom port\" field once → Connect (the shell remembers it)."
  fi
  echo "      Chrome/Brave/Edge ask once for \"Local network access\" — Allow, then Re-check."
}

ensure_ui() {
  if [ ! -f "$ROOT/dist-ui/manifest.json" ] || [ "$1" = "force" ]; then
    echo "▸ building the office UI (npm run build)"
    (cd "$ROOT" && npm run build >/dev/null)
  fi
}

# The PATH launchd hands a LaunchAgent is not your shell's. The first install
# on this Mac gave the office /opt/homebrew/bin and the system dirs, and the
# front desk reported every CLI as "not installed": Claude Code and Hermes
# live in ~/.local/bin, Codex in an nvm folder. So the office gets a PATH
# built from where the CLIs ARE right now, your login shell's PATH, and the
# usual places — deduplicated, in that order.
office_path() {
  local parts="" d c
  for c in claude codex gemini hermes node npm python3; do
    d="$(command -v "$c" 2>/dev/null || true)"
    [ -n "$d" ] && parts="$parts:$(dirname "$d")"
  done
  parts="$parts:$HOME/.local/bin:$(dirname "$PY")"
  parts="$parts:$("${SHELL:-/bin/zsh}" -lc 'echo "$PATH"' 2>/dev/null || true)"
  parts="$parts:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
  printf '%s' "$parts" | tr ':' '\n' | awk 'NF && !seen[$0]++' | paste -sd ':' -
}

write_plist() {
  mkdir -p "$AGENTS_DIR" "$LOG_DIR" "$STATE_DIR"
  local office_path_value
  office_path_value="$(office_path)"
  cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>$ROOT/serve.py</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PORT</key><string>$PORT</string>
    <key>CAFRESOHQ_HQ_STATE_DIR</key><string>$STATE_DIR</string>
    <key>HOME</key><string>$HOME</string>
    <key>PATH</key><string>$office_path_value</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>5</integer>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
PL
}

case "${1:-}" in
  install)
    [ -n "$PY" ] || { echo "local_hq.sh: no python3 on PATH" >&2; exit 1; }
    if port_in_use_by_other; then
      echo "local_hq.sh: port $PORT is already taken by another program (Docker forwards it for a container on this Mac?)." >&2
      echo "  pick another: PORT=8789 $0 install   — then type 8789 in the shell's custom port field once." >&2
      exit 1
    fi
    ensure_ui keep
    write_plist
    launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
    launchctl bootstrap "$DOMAIN" "$PLIST"
    echo "▸ LaunchAgent installed: $PLIST"
    for _ in $(seq 1 40); do
      if H="$(health)" && [ -n "$H" ]; then
        echo "✔ your office is up at http://localhost:$PORT"
        echo
        connect_hint
        exit 0
      fi
      sleep 0.5
    done
    echo "local_hq.sh: the office did not answer /health within 20s — see: $0 logs" >&2
    exit 1
    ;;
  uninstall)
    launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
    rm -f "$PLIST"
    echo "✔ LaunchAgent removed (the office state in $STATE_DIR is untouched)"
    ;;
  restart)
    ensure_ui force
    launchctl kickstart -k "$DOMAIN/$LABEL"
    sleep 2
    "$0" status
    ;;
  status)
    if H="$(health)" && [ -n "$H" ]; then
      echo "up   http://localhost:$PORT  $(printf '%s' "$H" | head -c 120)"
      launchctl print "$DOMAIN/$LABEL" 2>/dev/null | grep -E "state = |pid = " | sed 's/^/     /' || true
      connect_hint | sed 's/^/     /'
    else
      echo "down nothing of ours answers http://127.0.0.1:$PORT/health"
      [ -f "$PLIST" ] && echo "     the LaunchAgent is installed — try: $0 logs" || echo "     not installed — run: $0 install"
      exit 1
    fi
    ;;
  logs)
    tail -n 60 -f "$LOG"
    ;;
  run)
    ensure_ui keep
    cd "$ROOT" && PORT="$PORT" CAFRESOHQ_HQ_STATE_DIR="$STATE_DIR" exec "$PY" serve.py
    ;;
  plist)
    # print the LaunchAgent that `install` would write (no side effects)
    AGENTS_DIR="$(mktemp -d)"; PLIST="$AGENTS_DIR/$LABEL.plist"; LOG_DIR="$AGENTS_DIR"; LOG="$LOG_DIR/cafreso-hq.log"; STATE_DIR="${CAFRESOHQ_HQ_STATE_DIR:-$ROOT/hq-state}"
    mkdir -p "$STATE_DIR" 2>/dev/null || true
    write_plist; cat "$PLIST"; rm -rf "$AGENTS_DIR"
    ;;
  -h|--help|"")
    usage
    ;;
  *)
    echo "local_hq.sh: unknown command '$1'" >&2; usage >&2; exit 2
    ;;
esac
