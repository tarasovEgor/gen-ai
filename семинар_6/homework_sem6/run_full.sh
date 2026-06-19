#!/usr/bin/env bash
# Полный прогон для 8 баллов. Только один процесс — без параллельных LLM-задач.
set -euo pipefail
cd "$(dirname "$0")"
PY="uv run python"
LOG="output/run_all.log"
mkdir -p output

echo "=== START $(date) ===" | tee -a "$LOG"

echo "[1/3] Benchmark параллельности..." | tee -a "$LOG"
$PY benchmark_parallel.py 2>&1 | tee -a "$LOG"

echo "[2/3] Замер критики: 5 кейсов × 10 (T=0.0 и T=0.7)..." | tee -a "$LOG"
for i in 0 1 2 3 4; do
  echo "--- critic case $i ---" | tee -a "$LOG"
  $PY measure_critic.py --case "$i" -n 10 --pause 12 2>&1 | tee -a "$LOG"
  sleep 20
done

echo "[3/3] Eval: 6 вопросов × 3 конфигурации × N=3..." | tee -a "$LOG"
$PY eval_pwc.py -n 3 2>&1 | tee -a "$LOG"

echo "=== DONE $(date) ===" | tee -a "$LOG"
