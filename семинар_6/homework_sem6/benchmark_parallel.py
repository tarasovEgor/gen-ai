"""Замер ускорения execute_level (без полного PWC-цикла)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from orchestrator import _topological_levels, execute_level
from planner import planner
from retry_util import with_retry

BENCHMARKS = [
    {
        "name": "Q1_USD_ratio",
        "query": "Во сколько раз USD подорожал с 1 января 2022 по сегодня?",
    },
    {
        "name": "Q4_three_fx",
        "query": "Какие сегодня официальные курсы ЦБ для USD, EUR и CNY к рублю? Перечисли все три.",
    },
]


def bench_query(query: str) -> dict:
    plan = with_retry(lambda: planner(query))
    levels = _topological_levels(plan.subquestions)
    if not levels:
        return {"error": "пустой план", "levels": 0}

    level0 = levels[0]
    t0 = time.perf_counter()
    execute_level(level0, {}, parallel=False)
    seq = time.perf_counter() - t0

    t1 = time.perf_counter()
    execute_level(level0, {}, parallel=True)
    par = time.perf_counter() - t1

    return {
        "level0_size": len(level0),
        "sequential_sec": round(seq, 3),
        "parallel_sec": round(par, 3),
        "speedup": round(seq / par, 2) if par > 0 else 0.0,
        "subquestions": [sq.question for sq in level0],
    }


def main():
    path = Path(__file__).parent / "output" / "parallel_benchmark.json"
    path.parent.mkdir(exist_ok=True)
    out: dict = {}
    if path.exists():
        out = json.loads(path.read_text(encoding="utf-8"))

    for b in BENCHMARKS:
        if b["name"] in out and "error" not in out[b["name"]]:
            print(f"Benchmark: {b['name']} — уже есть, пропуск")
            continue
        print(f"Benchmark: {b['name']}...")
        out[b["name"]] = bench_query(b["query"])
        print(json.dumps(out[b["name"]], ensure_ascii=False, indent=2))
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nСохранено: {path}")


if __name__ == "__main__":
    main()
