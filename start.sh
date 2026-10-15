#!/usr/bin/env bash
# Modified for AI Drama Studio: starts `uv run drama-studio dev` + `pnpm -C web dev` (no pip / npm).
# AI Drama Studio launcher (Linux / macOS / Git Bash / WSL)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PORT="${PORT:-8000}"
WITH_WEB=1
SKIP_INSTALL=0

usage() {
  cat <<'EOF'
Usage: ./start.sh [options]

  --port PORT       Backend port (default: 8000; always bound to 127.0.0.1)
  --no-web          Backend only, no web workbench
  --skip-install    Do not run uv sync / pnpm install
  -h, --help        Show this help

Env:
  DRAMA_MOCK         Mock adapters unless set to 0 (0 = call real models)
  COMFYUI_URL        Default http://127.0.0.1:8188 if unset
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    --no-web) WITH_WEB=0; shift ;;
    --skip-install) SKIP_INSTALL=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1"; usage; exit 1 ;;
  esac
done

# .env (KEY=VALUE lines) for upstream settings such as COMFYUI_URL / FFMPEG_PATH; parsed, not
# sourced. API keys belong in the keyring (Models page); the backend also reads .env itself.
load_dotenv() {
  local line key val dq='"' sq="'"
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "${line// /}" || "${line:0:1}" == "#" || "$line" != *=* ]] && continue
    key="${line%%=*}"
    key="${key// /}"
    val="${line#*=}"
    if [[ "${val:0:1}" == "$dq" && "${val: -1}" == "$dq" ]] || [[ "${val:0:1}" == "$sq" && "${val: -1}" == "$sq" ]]; then
      val="${val:1:${#val}-2}"
    fi
    if [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      export "$key=$val"
    fi
  done < "$1"
}
if [[ -f "$ROOT/.env" ]]; then
  load_dotenv "$ROOT/.env"
fi
export DRAMA_SERIES_ROOT="$ROOT"
export COMFYUI_URL="${COMFYUI_URL:-http://127.0.0.1:8188}"
export DRAMA_BACKEND_URL="http://127.0.0.1:${PORT}"   # Vite proxies /api here
export COREPACK_ENABLE_DOWNLOAD_PROMPT=0

if ! command -v uv >/dev/null 2>&1; then
  echo "[ERROR] uv not found: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi
if [[ "$WITH_WEB" -eq 1 ]] && ! command -v corepack >/dev/null 2>&1; then
  echo "[ERROR] corepack not found. Install Node.js 24 (it ships corepack), or use --no-web."
  exit 1
fi

if [[ "$SKIP_INSTALL" -eq 0 ]]; then
  echo "[Setup] uv sync"
  uv sync
  if [[ "$WITH_WEB" -eq 1 ]]; then
    echo "[Setup] pnpm install (web/)"
    corepack pnpm -C web install --frozen-lockfile
  fi
fi

WEB_PID=""
cleanup() {
  if [[ -n "$WEB_PID" ]] && kill -0 "$WEB_PID" 2>/dev/null; then
    kill "$WEB_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

MOCK="on"
if [[ "${DRAMA_MOCK:-1}" == "0" ]]; then MOCK="off (real models)"; fi
echo "========================================"
echo "  AI Drama Studio"
echo "========================================"
echo "  API:   http://127.0.0.1:${PORT}   (docs: /docs)"
if [[ "$WITH_WEB" -eq 1 ]]; then echo "  Web:   http://127.0.0.1:5173"; fi
echo "  Mock:  $MOCK"
echo "  Comfy: $COMFYUI_URL"
echo "  Ctrl+C to stop"
echo "========================================"

if [[ "$WITH_WEB" -eq 1 ]]; then
  echo "[Starting] web workbench (pnpm -C web dev)"
  corepack pnpm -C web dev &
  WEB_PID=$!
fi

echo "[Starting] backend (uv run drama-studio dev)"
uv run drama-studio dev --port "$PORT"
