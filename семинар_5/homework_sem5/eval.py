"""
Оценка макро-агента: 10 вопросов (4 базовых + 6 своих).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import CACHE_STATS, run_agent

CASES = [
    {
        "id": 1,
        "query": "Какая сегодня ключевая ставка ЦБ?",
        "expected_tools": ["get_key_rate"],
        "must_have": [],
        "comment": "Базовый тест — один инструмент, одно число.",
    },
    {
        "id": 2,
        "query": "Сколько стоит доллар сегодня и сколько стоил 1 января 2022?",
        "expected_tools": ["get_fx_rate"],
        "must_have": [],
        "comment": "Два вызова одного инструмента с разными аргументами.",
    },
    {
        "id": 3,
        "query": "Какая сейчас реальная ключевая ставка? (номинальная минус инфляция г/г)",
        "expected_tools": ["get_key_rate", "get_inflation", "calculate"],
        "must_have": ["%"],
        "comment": "Три разных инструмента + арифметика.",
    },
    {
        "id": 4,
        "query": "Посчитай, за сколько лет удвоится вклад 100 тыс руб при текущей ключевой ставке (формула 72).",
        "expected_tools": ["get_key_rate", "calculate"],
        "must_have": ["год"],
        "comment": "Вычисление с формулой: 72 / ставка = годы.",
    },
    {
        "id": 5,
        "query": "Во сколько раз вырос курс USD с января 2022 по апрель 2026?",
        "expected_tools": ["compare_periods"],
        "must_have": [],
        "comment": "compare_periods: fx_USD, 2022-01 → 2026-04.",
    },
    {
        "id": 6,
        "query": "На сколько процентных пунктов изменилась ключевая ставка с июня 2022 по декабрь 2024?",
        "expected_tools": ["compare_periods"],
        "must_have": [],
        "comment": "compare_periods: key_rate, delta в п.п.",
    },
    {
        "id": 7,
        "query": "Какая была инфляция в феврале 2024 и безработица в том же месяце?",
        "expected_tools": ["get_inflation", "get_unemployment"],
        "must_have": ["%"],
        "comment": "Трудный: две разные метрики Росстата на один месяц — агент может перепутать год или вызвать только один инструмент.",
    },
    {
        "id": 8,
        "query": "Сколько юаней за доллар по кросс-курсу ЦБ на сегодня?",
        "expected_tools": ["get_fx_rate", "calculate"],
        "must_have": [],
        "comment": "Трудный: кросс-курс = USD/CNY через рубли; агент часто делит наоборот или забывает calculate.",
    },
    {
        "id": 9,
        "query": "Стоит ли сейчас брать ипотеку, если ключевая ставка выше инфляции?",
        "expected_tools": ["get_key_rate", "get_inflation"],
        "must_have": [],
        "comment": "Реальный вопрос: сравнение номинальной ставки и ИПЦ для решения о кредите.",
    },
    {
        "id": 10,
        "query": "Как изменилась безработица в России с конца 2022 по конец 2024?",
        "expected_tools": ["compare_periods"],
        "must_have": [],
        "comment": "Реальный вопрос: динамика рынка труда; compare_periods(unemployment).",
    },
]


def run_case(case: dict, *, use_cache: bool = False, track_cost: bool = False) -> dict:
    print(f"\n{'=' * 70}\n[Q{case['id']}] {case['query']}\n{'-' * 70}")
    res = run_agent(
        case["query"],
        max_iter=8,
        verbose=True,
        use_cache=use_cache,
        track_cost=track_cost,
    )
    used_tools = [e["call"] for e in res["trace"] if "call" in e]
    answer = res.get("answer") or ""

    tool_match = all(t in used_tools for t in case["expected_tools"])
    text_match = all(s.lower() in answer.lower() for s in case["must_have"])
    ok = bool(answer) and tool_match and text_match

    print(f"\n  tools used : {used_tools}")
    print(
        f"  expected    : {case['expected_tools']}  → {'OK' if tool_match else 'MISS'}"
    )
    print(f"  answer      : {answer[:200]}")
    print(f"  must_have   : {case['must_have']}  → {'OK' if text_match else 'MISS'}")
    print(f"  verdict     : {'PASS' if ok else 'FAIL'}")

    return {
        "id": case["id"],
        "query": case["query"],
        "ok": ok,
        "tools_used": used_tools,
        "steps": res["steps"],
        "answer": answer,
        "comment": case["comment"],
    }


def main():
    import argparse

    ap = argparse.ArgumentParser(description="Оценка макро-агента (10 вопросов)")
    ap.add_argument("--cache", action="store_true")
    ap.add_argument("--cost", action="store_true")
    ap.add_argument("--ids", type=str, default="", help="Только эти id через запятую, напр. 5,6")
    a = ap.parse_args()

    if a.cache:
        CACHE_STATS["hits"] = CACHE_STATS["misses"] = 0

    cases = CASES
    if a.ids.strip():
        wanted = {int(x) for x in a.ids.split(",")}
        cases = [c for c in CASES if c["id"] in wanted]

    results = [run_case(c, use_cache=a.cache, track_cost=a.cost) for c in cases]
    passed = sum(1 for r in results if r["ok"])

    print(f"\n{'=' * 70}\nИтого: {passed}/{len(cases)} пройдено")
    for r in results:
        mark = "[OK]  " if r["ok"] else "[FAIL]"
        print(f"  {mark} Q{r['id']} ({r['steps']} шагов) — {r['query'][:60]}")

    out = Path(__file__).parent / "output" / "eval_results.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nРезультаты: {out}")


if __name__ == "__main__":
    main()
