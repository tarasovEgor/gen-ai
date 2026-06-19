#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1
PY="uv run python"
mkdir -p output
LOG=output/complete.log

echo "=== COMPLETE RUN $(date) ===" | tee "$LOG"

echo "[1/3] Критик 5×10..." | tee -a "$LOG"
for i in 0 1 2 3 4; do
  echo "-- case $i $(date +%H:%M:%S) --" | tee -a "$LOG"
  $PY measure_critic.py --case "$i" -n 10 --pause 2 2>&1 | tee -a "$LOG" || true
done

echo "[2/3] Benchmark Q4..." | tee -a "$LOG"
$PY benchmark_parallel.py 2>&1 | tee -a "$LOG" || true

echo "[3/3] Eval 6×3 N=3 fast..." | tee -a "$LOG"
$PY eval_pwc.py -n 3 --fast 2>&1 | tee -a "$LOG" || true

echo "=== DONE $(date) ===" | tee -a "$LOG"