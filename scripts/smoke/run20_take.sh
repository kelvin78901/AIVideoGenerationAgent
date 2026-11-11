#!/bin/sh
# Usage: take.sh 1-05 — one run-20 take, then its check lines.
cd /c/dev/drama-studio || exit 1
L="$1"
PYTHONIOENCODING=utf-8 DRAMA_LIVE=1 uv run --no-sync python scripts/smoke/local_video.py --only episode --home "$TEMP/drama-ep20b/home" --from "$L" --to "$L" --run run20-fresh --takes 1 > "$TEMP/drama-ep20b/take-$L.log" 2>&1
echo "exit $?"
grep -E "call comfy|检查|adopted|no takes|Traceback|Error" "$TEMP/drama-ep20b/take-$L.log" | head -8
