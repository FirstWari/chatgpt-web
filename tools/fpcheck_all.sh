#!/bin/bash
# Run every mode against every site. Usage: fpcheck_all.sh [site ...]
# Results: $STATE/debug/fp/<stamp>/<site-key>/<mode>/{page.txt,shot.png}
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="${CHATGPT_STATE_DIR:-$HOME/work/chatgpt-web}"
STAMP="$(date +%Y%m%d-%H%M%S)"
PY="$HERE/../.venv/bin/python"
WAIT="${WAIT:-25}"
declare -A SITES=(
  [brotector]="https://ttlns.github.io/brotector/"
  [rebrowser]="https://bot-detector.rebrowser.net/"
  [browserscan]="https://www.browserscan.net/bot-detection"
  [creepjs]="https://abrahamjuliot.github.io/creepjs/"
  [turnstile]="https://nopecha.com/demo/turnstile"
)
KEYS=("$@"); [ ${#KEYS[@]} -eq 0 ] && KEYS=(brotector rebrowser browserscan turnstile)
for k in "${KEYS[@]}"; do
  url="${SITES[$k]}"
  for mode in raw playwright patchright; do
    out="$ROOT/debug/fp/$STAMP/$k/$mode"
    if [ "$mode" = raw ]; then node "$HERE/fpcheck_raw.mjs" "$url" "$out" "$WAIT"
    else "$PY" "$HERE/fpcheck.py" --mode "$mode" --url "$url" --out "$out" --wait "$WAIT"; fi
    sleep 3
  done
done
echo "RESULTS: $ROOT/debug/fp/$STAMP"
