#!/usr/bin/env bash
# Последовательный прогон всех замеров (без параллельных процессов — меньше 429).
set -euo pipefail
cd "$(dirname "$0")"
PY="uv run python"

echo "1. Benchmark параллельности..."
$PY benchmark_parallel.py

echo "2. Замер критики (5 кейсов × 10, пауза 10с)..."
for i in 0 1 2 3 4; do
  $PY measure_critic.py --case "$i" -n 10 --pause 10
  sleep 30
done

echo "3. Eval 6×3, N=3..."
$PY eval_pwc.py -n 3

echo "Готово. См. output/ и отчет.md"
