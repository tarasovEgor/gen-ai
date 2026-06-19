"""
Оркестратор PWC: валидатор схемы, параллельные уровни, replan/rework.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from critic import critic
from llm_client import get_model, make_raw_client
from planner import planner
from retry_util import with_retry
from schemas_pwc import Plan, SubQuestion, WorkerAnswer
from worker import worker

VALID_TOOLS = {"get_fx_rate", "get_key_rate", "get_inflation", "calculate"}


def validate_plan(plan: Plan) -> list[str]:
    """Вернуть список ошибок плана (пустой — всё ок)."""
    errors: list[str] = []
    ids = {sq.id for sq in plan.subquestions}

    for sq in plan.subquestions:
        if not sq.expected_tools:
            errors.append(f"подвопрос {sq.id}: пустой expected_tools")
        for tool in sq.expected_tools:
            if tool not in VALID_TOOLS:
                errors.append(
                    f"подвопрос {sq.id}: неизвестный инструмент {tool!r} "
                    f"(допустимо: {sorted(VALID_TOOLS)})"
                )
        for dep in sq.depends_on:
            if dep not in ids:
                errors.append(f"подвопрос {sq.id}: depends_on ссылается на несуществующий id={dep}")
            if dep == sq.id:
                errors.append(f"подвопрос {sq.id}: depends_on ссылается на самого себя")

    return errors


def _topological_levels(subqs: list[SubQuestion]) -> list[list[SubQuestion]]:
    """Разбить подвопросы на уровни: внутри уровня зависимостей нет."""
    if not subqs:
        return []

    by_id = {s.id: s for s in subqs}
    depth: dict[int, int] = {}

    def depth_of(node_id: int, path: set[int]) -> int:
        if node_id in depth:
            return depth[node_id]
        if node_id not in by_id:
            return 0
        if node_id in path:
            raise ValueError(f"Цикл в depends_on: {sorted(path | {node_id})}")
        deps = [d for d in by_id[node_id].depends_on if d in by_id]
        depth[node_id] = 0 if not deps else 1 + max(depth_of(d, path | {node_id}) for d in deps)
        return depth[node_id]

    for sq in subqs:
        depth_of(sq.id, set())

    max_d = max(depth.values())
    levels: list[list[SubQuestion]] = [[] for _ in range(max_d + 1)]
    for sq in subqs:
        levels[depth[sq.id]].append(sq)
    return [lvl for lvl in levels if lvl]


def execute_level(
    level: list[SubQuestion],
    prev_answers: dict[int, WorkerAnswer],
    *,
    parallel: bool = True,
) -> dict[int, WorkerAnswer]:
    """Прогнать все подвопросы уровня (параллельно или последовательно)."""
    if not level:
        return {}

    if not parallel or len(level) == 1:
        return {sq.id: worker(sq, prev_answers) for sq in level}

    out: dict[int, WorkerAnswer] = {}
    with ThreadPoolExecutor(max_workers=min(len(level), 4)) as ex:
        futures = {ex.submit(worker, sq, prev_answers): sq for sq in level}
        for fut in as_completed(futures):
            sq = futures[fut]
            out[sq.id] = fut.result()
    return out


def _synthesize(
    question: str,
    plan: Plan,
    answers: dict[int, WorkerAnswer],
    *,
    fast: bool = False,
) -> str:
    """Собрать финальный ответ. fast=True — склейка без LLM."""
    if fast or not answers:
        return " · ".join(answers[i].answer for i in sorted(answers))
    client = make_raw_client()
    model = get_model()
    facts = "\n".join(
        f"{i}. {answers[i].answer}" for i in sorted(answers) if i in answers
    )
    prompt = (
        f"Исходный вопрос: {question}\n\n"
        f"План: {plan.reasoning}\n\n"
        f"Факты от исполнителей:\n{facts or '(нет)'}\n\n"
        "Собери один короткий ответ пользователю (1-2 фразы) с числами и единицами. "
        "Не придумывай новых чисел."
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
    )
    return (resp.choices[0].message.content or "").strip() or " · ".join(
        answers[i].answer for i in sorted(answers)
    )


def _plan_with_validation(
    question: str,
    *,
    use_validator: bool,
    feedback: str | None = None,
    verbose: bool,
) -> Plan:
    plan = planner(question, feedback=feedback)
    if not use_validator:
        return plan

    errors = validate_plan(plan)
    if errors:
        if verbose:
            print(f"  [validator] отклонён план: {errors}")
        plan = planner(question, feedback=f"Инструменты не существуют: {errors}")
        errors2 = validate_plan(plan)
        if errors2 and verbose:
            print(f"  [validator] повторно: {errors2}")
    return plan


def run_pwc(
    question: str,
    *,
    max_iter: int = 3,
    verbose: bool = True,
    use_validator: bool = True,
    parallel: bool = True,
    fast_synthesize: bool = False,
    skip_critic: bool = False,
) -> dict[str, Any]:
    """Запустить цикл Планировщик-Исполнитель-Критик."""
    trace: list[dict[str, Any]] = []
    t0 = time.perf_counter()

    plan = _plan_with_validation(question, use_validator=use_validator, verbose=verbose)
    trace.append(
        {
            "kind": "plan",
            "reasoning": plan.reasoning,
            "subquestions": [sq.model_dump() for sq in plan.subquestions],
            "validator": use_validator,
            "plan_errors": validate_plan(plan),
        }
    )

    if verbose:
        print(f"\n[plan] {plan.reasoning}")
        for sq in plan.subquestions:
            print(f"  {sq.id}. [{','.join(sq.expected_tools)}] {sq.question}")

    answers: dict[int, WorkerAnswer] = {}

    for iter_num in range(1, max_iter + 1):
        answers = {}
        levels = _topological_levels(plan.subquestions)
        for level in levels:
            level_answers = execute_level(level, answers, parallel=parallel)
            answers.update(level_answers)
            for sq in level:
                ans = answers[sq.id]
                trace.append(
                    {
                        "iter": iter_num,
                        "kind": "worker",
                        "sq_id": sq.id,
                        "used_tools": ans.used_tools,
                        "answer": ans.answer,
                        "parallel": parallel,
                    }
                )
                if verbose:
                    print(f"  [{sq.id}] → {ans.answer}   tools={ans.used_tools}")

        if skip_critic:
            has_err = any("(ошибка" in a.answer.lower() for a in answers.values())
            verdict_ok = bool(answers) and not has_err
            trace.append(
                {
                    "iter": iter_num,
                    "kind": "verdict",
                    "ok": verdict_ok,
                    "action": "accept" if verdict_ok else "replan",
                    "reason": "skip_critic: auto",
                    "rework_ids": [],
                }
            )
            if verdict_ok:
                final = _synthesize(question, plan, answers, fast=fast_synthesize)
                return {
                    "answer": final,
                    "plan": plan,
                    "answers": answers,
                    "trace": trace,
                    "iterations": iter_num,
                    "elapsed_sec": round(time.perf_counter() - t0, 3),
                    "parallel": parallel,
                    "use_validator": use_validator,
                }
            break

        verdict = critic(question, plan, answers)
        trace.append(
            {
                "iter": iter_num,
                "kind": "verdict",
                "ok": verdict.ok,
                "action": verdict.action,
                "reason": verdict.reason,
                "rework_ids": verdict.rework_ids,
            }
        )

        if verbose:
            mark = "✅" if verdict.ok else "❌"
            print(f"  [critic {mark}] {verdict.action}: {verdict.reason}")

        if verdict.ok:
            final = _synthesize(question, plan, answers, fast=fast_synthesize)
            return {
                "answer": final,
                "plan": plan,
                "answers": answers,
                "trace": trace,
                "iterations": iter_num,
                "elapsed_sec": round(time.perf_counter() - t0, 3),
                "parallel": parallel,
                "use_validator": use_validator,
            }

        if verdict.action == "replan":
            plan = _plan_with_validation(
                question,
                use_validator=use_validator,
                feedback=verdict.reason,
                verbose=verbose,
            )
            trace.append({"kind": "replan", "reason": verdict.reason})
            continue

        if verdict.action == "rework":
            fb = f"Переделать подвопросы {verdict.rework_ids}: {verdict.reason}"
            plan = _plan_with_validation(
                question,
                use_validator=use_validator,
                feedback=fb,
                verbose=verbose,
            )
            trace.append({"kind": "rework", "rework_ids": verdict.rework_ids})
            continue

        break

    return {
        "answer": None,
        "error": f"не удалось получить вердикт 'accept' за {max_iter} итераций",
        "plan": plan,
        "answers": answers,
        "trace": trace,
        "iterations": max_iter,
        "elapsed_sec": round(time.perf_counter() - t0, 3),
        "parallel": parallel,
        "use_validator": use_validator,
    }


def benchmark_parallel(question: str, *, repeats: int = 1) -> dict[str, float]:
    """Сравнить время последовательного и параллельного исполнения."""
    times_seq: list[float] = []
    times_par: list[float] = []
    for _ in range(repeats):
        r_seq = with_retry(
            lambda: run_pwc(question, max_iter=1, verbose=False, parallel=False, use_validator=True)
        )
        times_seq.append(r_seq["elapsed_sec"])
        r_par = with_retry(
            lambda: run_pwc(question, max_iter=1, verbose=False, parallel=True, use_validator=True)
        )
        times_par.append(r_par["elapsed_sec"])
    seq = sum(times_seq) / len(times_seq)
    par = sum(times_par) / len(times_par)
    return {
        "sequential_sec": round(seq, 3),
        "parallel_sec": round(par, 3),
        "speedup": round(seq / par, 2) if par > 0 else 0.0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="+", help="Вопрос к агенту")
    ap.add_argument("--max-iter", type=int, default=3)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--no-validator", action="store_true")
    ap.add_argument("--sequential", action="store_true", help="без параллели на уровне")
    ap.add_argument("--benchmark", action="store_true", help="замер seq vs par")
    ap.add_argument("--trace", type=Path, default=None)
    args = ap.parse_args()

    q = " ".join(args.query)

    if args.benchmark:
        b = benchmark_parallel(q)
        print(json.dumps(b, ensure_ascii=False, indent=2))
        return

    res = run_pwc(
        q,
        max_iter=args.max_iter,
        verbose=not args.quiet,
        use_validator=not args.no_validator,
        parallel=not args.sequential,
    )

    print("\n=== ВОПРОС ===")
    print(q)
    print("\n=== ОТВЕТ ===")
    print(res.get("answer") or res.get("error"))
    print(f"\n(итераций: {res.get('iterations', '?')}, {res.get('elapsed_sec', '?')} с)")

    if args.trace:
        args.trace.write_text(
            json.dumps({"query": q, **_serialize(res)}, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"Трейс сохранён: {args.trace}")


def _serialize(res: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in res.items():
        if k == "plan" and v is not None:
            out[k] = v.model_dump()
        elif k == "answers":
            out[k] = {i: a.model_dump() for i, a in v.items()}
        else:
            out[k] = v
    return out


if __name__ == "__main__":
    main()
