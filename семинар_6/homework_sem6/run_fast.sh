#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PY="uv run python"
mkdir -p output

echo "=== FAST $(date) ===" | tee output/fast.log

echo "[1/2] Критик: 5 кейсов × 10..." | tee -a output/fast.log
for i in 0 1 2 3 4; do
  $PY measure_critic.py --case "$i" -n 10 --pause 1 2>&1 | tee -a output/fast.log
done

echo "[2/2] Eval: 6×3, N=3, --fast..." | tee -a output/fast.log
$PY eval_pwc.py -n 3 --fast 2>&1 | tee -a output/fast.log

echo "=== DONE $(date) ===" | tee -a output/fast.log