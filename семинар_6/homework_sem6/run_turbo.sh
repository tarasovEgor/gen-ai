#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1
PY="uv run python"
mkdir -p output
LOG=output/turbo.log

echo "=== DEADLINE $(date) ===" | tee "$LOG"

echo "[1/2] Критик 5×10 (rules, без API)..." | tee -a "$LOG"
$PY measure_critic.py --rules -n 10 2>&1 | tee -a "$LOG"

echo "[2/2] Eval 6×3 turbo..." | tee -a "$LOG"
$PY eval_pwc.py -n 3 --turbo 2>&1 | tee -a "$LOG" || true

echo "=== DONE $(date) ===" | tee -a "$LOG"