"""
Eval PWC: 6 вопросов × 3 конфигурации (single / pwc / pwc+validator).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_s5 import run_agent
from orchestrator import run_pwc
from retry_util import with_retry

CASES = [
    {
        "id": "Q1",
        "query": "Во сколько раз USD подорожал с 1 января 2022 по сегодня?",
        "comment": "Ошибка C: нужен calculate. Параллельность: 2 независимых get_fx_rate.",
        "must_have_keywords": ["раз", "usd"],
        "forbid_hallucinated_tools": True,
        "needs_calculate": True,
    },
    {
        "id": "Q2",
        "query": (
            "Какая сейчас реальная ключевая ставка, если инфляцию брать "
            "по последнему доступному месяцу, а не по году?"
        ),
        "comment": "Ошибка B: последний доступный месяц ИПЦ.",
        "must_have_keywords": ["%"],
        "forbid_hallucinated_tools": True,
        "needs_calculate": True,
    },
    {
        "id": "Q3",
        "query": (
            "Какова накопленная инфляция с января 2022 по март 2026? "
            "Рассчитай как произведение всех (1 + ипц_м/100) по месяцам."
        ),
        "comment": "Валидатор ловит get_cumulative_inflation в плане.",
        "must_have_keywords": ["%"],
        "forbid_hallucinated_tools": True,
        "needs_calculate": False,
        "validator_fixes": True,
    },
    {
        "id": "Q4",
        "query": (
            "Какие сегодня официальные курсы ЦБ для USD, EUR и CNY к рублю? "
            "Перечисли все три."
        ),
        "comment": "Параллельность: 3 независимых подвопроса на одном уровне.",
        "must_have_keywords": ["usd", "eur", "cny"],
        "forbid_hallucinated_tools": True,
        "needs_calculate": False,
        "parallel_benchmark": True,
    },
    {
        "id": "Q5",
        "query": (
            "Стоит ли сейчас держать сбережения в рублях: "
            "ключевая ставка выше инфляции за последний доступный месяц?"
        ),
        "comment": "Реальный вопрос: сравнение ставки и ИПЦ для решения о сбережениях.",
        "must_have_keywords": ["%"],
        "forbid_hallucinated_tools": True,
        "needs_calculate": False,
    },
    {
        "id": "Q6",
        "query": (
            "На сколько процентных пунктов изменилась ключевая ставка "
            "с июня 2022 по декабрь 2024?"
        ),
        "comment": "Два get_key_rate + calculate; PWC с валидатором.",
        "must_have_keywords": ["%"],
        "forbid_hallucinated_tools": True,
        "needs_calculate": True,
    },
]

VALID_TOOL_NAMES = {"get_fx_rate", "get_key_rate", "get_inflation", "calculate"}


def _check_single(case: dict, result: dict) -> dict:
    used = {e["call"] for e in result.get("trace", []) if "call" in e}
    ans = (result.get("answer") or "").lower()
    hallucinated = used - VALID_TOOL_NAMES
    must = all(kw.lower() in ans for kw in case["must_have_keywords"])
    arith_without_calc = case.get("needs_calculate") and "calculate" not in used and bool(ans)
    ok = bool(ans) and not hallucinated and must and not arith_without_calc
    return {
        "ok": ok,
        "used_tools": sorted(used),
        "hallucinated": sorted(hallucinated),
        "must_have_ok": must,
        "answer_preview": (result.get("answer") or "")[:160],
    }


def _check_pwc(case: dict, result: dict, *, with_validator: bool) -> dict:
    used: set[str] = set()
    for t in result.get("trace", []):
        if t.get("kind") == "worker":
            used.update(t.get("used_tools") or [])
    ans = (result.get("answer") or "").lower()
    hallucinated = used - VALID_TOOL_NAMES

    plan_tools: set[str] = set()
    plan = result.get("plan")
    if plan is not None:
        for sq in plan.subquestions:
            plan_tools.update(sq.expected_tools)
    plan_hallucinated = plan_tools - VALID_TOOL_NAMES

    must = all(kw.lower() in ans for kw in case["must_have_keywords"])

    # Q3: успех с валидатором = нет галлюцинаций в плане (честный план или пустой)
    if case.get("validator_fixes") and with_validator:
        ok = not plan_hallucinated and not hallucinated
    else:
        ok = bool(result.get("answer")) and not hallucinated and not plan_hallucinated and must

    return {
        "ok": ok,
        "used_tools": sorted(used),
        "plan_tools": sorted(plan_tools),
        "hallucinated_in_plan": sorted(plan_hallucinated),
        "must_have_ok": must,
        "answer_preview": (result.get("answer") or "")[:160],
    }


def run_case(case: dict, *, n: int = 5, fast: bool = False, turbo: bool = False) -> dict:
    single = {"runs": [], "pass": 0}
    pwc_raw = {"runs": [], "pass": 0}
    pwc_val = {"runs": [], "pass": 0}
    single_iter = 4 if turbo else (5 if fast else 8)
    pwc_iter = 1 if turbo else (2 if fast else 3)
    pause = 0 if (fast or turbo) else 4
    skip_critic = turbo

    for _ in range(n):
        try:
            r1 = with_retry(lambda: run_agent(case["query"], max_iter=single_iter, verbose=False))
        except Exception as e:
            r1 = {"answer": None, "error": str(e), "trace": []}
        c1 = _check_single(case, r1)
        single["runs"].append(c1)
        single["pass"] += int(c1["ok"])
        if pause:
            time.sleep(pause)

        try:
            r2 = with_retry(
                lambda: run_pwc(
                    case["query"],
                    max_iter=pwc_iter,
                    verbose=False,
                    use_validator=False,
                    parallel=True,
                    fast_synthesize=fast or turbo,
                    skip_critic=skip_critic,
                )
            )
        except Exception as e:
            r2 = {"answer": None, "error": str(e), "trace": [], "plan": None}
        c2 = _check_pwc(case, r2, with_validator=False)
        pwc_raw["runs"].append(c2)
        pwc_raw["pass"] += int(c2["ok"])
        if pause:
            time.sleep(pause)

        try:
            r3 = with_retry(
                lambda: run_pwc(
                    case["query"],
                    max_iter=pwc_iter,
                    verbose=False,
                    use_validator=True,
                    parallel=True,
                    fast_synthesize=fast or turbo,
                    skip_critic=skip_critic,
                )
            )
        except Exception as e:
            r3 = {"answer": None, "error": str(e), "trace": [], "plan": None}
        c3 = _check_pwc(case, r3, with_validator=True)
        pwc_val["runs"].append(c3)
        pwc_val["pass"] += int(c3["ok"])
        if pause:
            time.sleep(pause)

    return {
        "id": case["id"],
        "query": case["query"],
        "comment": case["comment"],
        "n": n,
        "single": single,
        "pwc_no_validator": pwc_raw,
        "pwc_validator": pwc_val,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--single", action="store_true", help="1 прогон на кейс")
    ap.add_argument("-n", type=int, default=5)
    ap.add_argument("--fast", action="store_true", help="без пауз, короткие итерации, склейка без LLM")
    ap.add_argument("--turbo", action="store_true", help="fast + skip critic LLM в PWC (ещё быстрее eval)")
    ap.add_argument("--ids", type=str, default="", help="Q1,Q3,...")
    args = ap.parse_args()
    n = 1 if args.single else max(args.n, 3)

    cases = CASES
    if args.ids.strip():
        wanted = {x.strip() for x in args.ids.split(",")}
        cases = [c for c in CASES if c["id"] in wanted]

    print(f"Eval С6: {len(cases)} кейсов × {n} × 3{' [TURBO]' if args.turbo else (' [FAST]' if args.fast else '')}\n")
    results = []
    out = Path(__file__).parent / "output" / "eval_pwc_results.json"
    out.parent.mkdir(exist_ok=True)
    for c in cases:
        r = run_case(c, n=n, fast=args.fast or args.turbo, turbo=args.turbo)
        results.append(r)
        out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            f"  {r['id']}: single {r['single']['pass']}/{n}  "
            f"pwc {r['pwc_no_validator']['pass']}/{n}  "
            f"pwc+val {r['pwc_validator']['pass']}/{n}"
        )

    print("=" * 72)
    print(f"{'id':<4} {'single':>8} {'pwc':>8} {'pwc+val':>8}  query")
    print("-" * 72)
    for r in results:
        print(
            f"{r['id']:<4} {r['single']['pass']}/{n:>6} "
            f"{r['pwc_no_validator']['pass']}/{n:>6} "
            f"{r['pwc_validator']['pass']}/{n:>6}  {r['query'][:45]}..."
        )

    out = Path(__file__).parent / "output" / "eval_pwc_results.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nРезультаты: {out}")


if __name__ == "__main__":
    main()
