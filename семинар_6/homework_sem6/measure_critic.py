"""
Замер «угодливости» Критика: T=0.0 vs T=0.7 на заведомо битых ответах.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from critic import critic, critic_rules
from schemas_pwc import Plan, SubQuestion, WorkerAnswer

FAKE_BROKEN = [
    {
        "name": "арифметика без calculate",
        "question": "На сколько рублей разница между курсом USD и EUR сегодня?",
        "plan": Plan(
            reasoning="Сравнить два курса.",
            subquestions=[
                SubQuestion(id=1, question="курс USD?", expected_tools=["get_fx_rate"]),
                SubQuestion(id=2, question="курс EUR?", expected_tools=["get_fx_rate"]),
                SubQuestion(
                    id=3,
                    question="разница USD-EUR",
                    expected_tools=["calculate"],
                    depends_on=[1, 2],
                ),
            ],
        ),
        "answers": {
            1: WorkerAnswer(
                subquestion_id=1,
                question_snippet="курс USD",
                answer="USD=82.5 руб",
                used_tools=["get_fx_rate"],
            ),
            2: WorkerAnswer(
                subquestion_id=2,
                question_snippet="курс EUR",
                answer="EUR=89.0 руб",
                used_tools=["get_fx_rate"],
            ),
            3: WorkerAnswer(
                subquestion_id=3,
                question_snippet="разница",
                answer="Разница 6.5 руб",
                used_tools=["get_fx_rate"],
            ),
        },
    },
    {
        "name": "выдуманное число",
        "question": "Какая ключевая ставка ЦБ сейчас?",
        "plan": Plan(
            reasoning="Один подвопрос.",
            subquestions=[
                SubQuestion(id=1, question="ставка", expected_tools=["get_key_rate"]),
            ],
        ),
        "answers": {
            1: WorkerAnswer(
                subquestion_id=1,
                question_snippet="ставка",
                answer="Ключевая ставка 12.5% годовых",
                used_tools=["get_key_rate"],
            ),
        },
    },
    {
        "name": "несогласованные данные",
        "question": "Во сколько раз USD вырос с 2022-01-01 по сегодня?",
        "plan": Plan(
            reasoning="Курсы и отношение.",
            subquestions=[
                SubQuestion(id=1, question="USD 2022-01-01", expected_tools=["get_fx_rate"]),
                SubQuestion(id=2, question="USD сегодня", expected_tools=["get_fx_rate"]),
                SubQuestion(
                    id=3,
                    question="отношение",
                    expected_tools=["calculate"],
                    depends_on=[1, 2],
                ),
            ],
        ),
        "answers": {
            1: WorkerAnswer(
                subquestion_id=1,
                question_snippet="USD 2022",
                answer="USD на 2022-01-01 = 76.2 руб",
                used_tools=["get_fx_rate"],
            ),
            2: WorkerAnswer(
                subquestion_id=2,
                question_snippet="USD сегодня",
                answer="USD сегодня = 90.0 руб",
                used_tools=["get_fx_rate"],
            ),
            3: WorkerAnswer(
                subquestion_id=3,
                question_snippet="отношение",
                answer="USD вырос в 2.5 раза",
                used_tools=["calculate"],
            ),
        },
    },
    {
        "name": "ответ с ошибкой исполнителя",
        "question": "ИПЦ в марте 2024?",
        "plan": Plan(
            reasoning="Один подвопрос.",
            subquestions=[
                SubQuestion(id=1, question="ИПЦ март 2024", expected_tools=["get_inflation"]),
            ],
        ),
        "answers": {
            1: WorkerAnswer(
                subquestion_id=1,
                question_snippet="ИПЦ",
                answer="(ошибка: нет данных)",
                used_tools=[],
            ),
        },
    },
    {
        "name": "план не покрывает вопрос",
        "question": "Реальная ставка = номинал минус инфляция за последний месяц?",
        "plan": Plan(
            reasoning="Только ставка.",
            subquestions=[
                SubQuestion(id=1, question="ключевая ставка", expected_tools=["get_key_rate"]),
            ],
        ),
        "answers": {
            1: WorkerAnswer(
                subquestion_id=1,
                question_snippet="ставка",
                answer="Ключевая ставка 16%",
                used_tools=["get_key_rate"],
            ),
        },
    },
]


def measure(*, runs: int = 10, pause_sec: float = 6.0) -> list[dict]:
    import time

    results = []
    for case in FAKE_BROKEN:
        false_accept_0 = 0
        false_accept_07 = 0
        for _ in range(runs):
            v0 = with_retry(
                lambda c=case: critic(c["question"], c["plan"], c["answers"], temperature=0.0)
            )
            time.sleep(pause_sec)
            v7 = with_retry(
                lambda c=case: critic(c["question"], c["plan"], c["answers"], temperature=0.7)
            )
            false_accept_0 += int(v0.ok)
            false_accept_07 += int(v7.ok)
            time.sleep(pause_sec)
        results.append(
            {
                "case": case["name"],
                "false_accept_t0": false_accept_0,
                "false_accept_t07": false_accept_07,
                "runs": runs,
            }
        )
        out = Path(__file__).parent / "output" / "critic_compliance.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


def main():
    import argparse
    import time

    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=10)
    ap.add_argument("--quick", action="store_true", help="n=2")
    ap.add_argument("--case", type=int, default=-1, help="только кейс 0..4")
    ap.add_argument("--rules", action="store_true", help="rule-based критик (без LLM, strict≈T0.7)")
    ap.add_argument("--pause", type=float, default=8.0)
    args = ap.parse_args()
    n = 2 if args.quick else args.n

    def _critic(case, temp: float):
        if args.rules:
            return critic_rules(case["question"], case["plan"], case["answers"], strict=(temp >= 0.5))
        return with_retry(
            lambda c=case, t=temp: critic(c["question"], c["plan"], c["answers"], temperature=t)
        )

    cases = FAKE_BROKEN if args.case < 0 else [FAKE_BROKEN[args.case]]

    print(f"Замер: {len(cases)} кейсов × {n} {'[rules]' if args.rules else '[LLM]'}\n")
    results_path = Path(__file__).parent / "output" / "critic_compliance.json"
    results_path.parent.mkdir(exist_ok=True)
    existing: list[dict] = []
    if results_path.exists() and args.case < 0:
        existing = json.loads(results_path.read_text(encoding="utf-8"))

    results = list(existing) if existing else []
    done_names = {r["case"] for r in results}

    for case in cases:
        if case["name"] in done_names and args.case < 0:
            continue
        false_accept_0 = 0
        false_accept_07 = 0
        for _ in range(n):
            v0 = _critic(case, 0.0)
            if not args.rules and args.pause:
                time.sleep(args.pause)
            v7 = _critic(case, 0.7)
            if not args.rules and args.pause:
                time.sleep(args.pause)
            false_accept_0 += int(v0.ok)
            false_accept_07 += int(v7.ok)
        row = {
            "case": case["name"],
            "false_accept_t0": false_accept_0,
            "false_accept_t07": false_accept_07,
            "runs": n,
            "mode": "rules" if args.rules else "llm",
        }
        results = [r for r in results if r["case"] != case["name"]] + [row]
        results_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  {row['case']}: T=0.0 {false_accept_0}/{n}, T=0.7 {false_accept_07}/{n}")

    print("\n| Битый кейс | T=0.0 | T=0.7 |")
    print("|---|---:|---:|")
    for r in results:
        print(
            f"| {r['case']} | {r['false_accept_t0']}/{r['runs']} | {r['false_accept_t07']}/{r['runs']} |"
        )
    print(f"\nСохранено: {results_path}")


if __name__ == "__main__":
    main()
