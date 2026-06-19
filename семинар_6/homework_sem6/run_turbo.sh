#!/usr/bin/env bash
# Дедлайн: критик первым (~10 мин), eval вторым (~20 мин).
set -uo pipefail
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1
PY="uv run python"
mkdir -p output
LOG=output/turbo.log

echo "=== DEADLINE $(date) ===" | tee "$LOG"

echo "[1/2] Критик 5×10..." | tee -a "$LOG"
for i in 0 1 2 3 4; do
  echo "-- case $i $(date +%H:%M) --" | tee -a "$LOG"
  $PY measure_critic.py --case "$i" -n 10 --pause 0 2>&1 | tee -a "$LOG" || true
done

echo "[2/2] Eval 6×3 turbo..." | tee -a "$LOG"
$PY eval_pwc.py -n 3 --turbo 2>&1 | tee -a "$LOG" || true

echo "=== DONE $(date) ===" | tee -a "$LOG"