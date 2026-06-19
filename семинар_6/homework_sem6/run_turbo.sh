#!/usr/bin/env bash
# Дедлайн-режим: сначала eval (2 балла), потом критик (2 балла).
set -euo pipefail
cd "$(dirname "$0")"
PY="uv run python"
mkdir -p output
LOG=output/turbo.log

echo "=== DEADLINE RUN $(date) ===" | tee "$LOG"

echo "[1/2] Eval 6×3 N=3 turbo (~15 мин)..." | tee -a "$LOG"
$PY eval_pwc.py -n 3 --turbo 2>&1 | tee -a "$LOG"

echo "[2/2] Критик 5×10 (~10 мин)..." | tee -a "$LOG"
for i in 0 1 2 3 4; do
  echo "-- case $i --" | tee -a "$LOG"
  $PY measure_critic.py --case "$i" -n 10 --pause 0 2>&1 | tee -a "$LOG"
done

echo "=== DONE $(date) ===" | tee -a "$LOG"
