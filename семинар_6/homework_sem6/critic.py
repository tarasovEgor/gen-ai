"""
Критик: независимый проверяющий ответов исполнителей.
"""

from __future__ import annotations

from llm_client import get_model, make_client
from schemas_pwc import Plan, Verdict, WorkerAnswer

CRITIC_PROMPT = """\
Ты — критик мульти-агентной системы. Твоя работа — убедиться, что ответы
отвечают на исходный вопрос, согласованы между собой и получены честно.

Исходный вопрос пользователя:
  «{question}»

План, по которому работала система:
{plan_text}

Ответы Исполнителей (финальные, без трейса):
{answers_text}

Проверь ПОШАГОВО:
1. Все ли числа получены через calculate? Если в финальном ответе
   есть производное число (разность, отношение, произведение), но в
   used_tools соответствующего подвопроса НЕТ «calculate» — это БРАК.
2. Согласованы ли числа между подвопросами, на которые ссылаются последующие?
3. Покрывает ли план ВЕСЬ исходный вопрос? Если часть осталась без
   ответа — это replan.
4. Нет ли ответов вида «(ошибка: ...)» — они автоматически БРАК.

Вердикт:
- ok=True, action=accept — если всё чисто.
- ok=False, action=rework, rework_ids=[X] — если конкретные подвопросы
  нужно переделать.
- ok=False, action=replan — если план в принципе не охватывает вопрос.
"""


def critic_rules(
    question: str,
    plan: Plan,
    answers: dict[int, WorkerAnswer],
    *,
    strict: bool,
) -> Verdict:
    """Детерминированные правила из CRITIC_PROMPT. strict=True ≈ T=0.7, strict=False ≈ T=0.0."""
    import re

    issues: list[str] = []
    rework: list[int] = []

    plan_tools = {t for sq in plan.subquestions for t in sq.expected_tools}
    q = question.lower()

    for sq in plan.subquestions:
        a = answers.get(sq.id)
        if a is None:
            continue
        if "(ошибка" in a.answer.lower():
            issues.append(f"sq{sq.id}: ошибка исполнителя")
            rework.append(sq.id)
        if "calculate" in sq.expected_tools and "calculate" not in a.used_tools and strict:
            issues.append(f"sq{sq.id}: производное число без calculate")
            rework.append(sq.id)

    # Согласованность: 90/76.2 ≈ 1.18, не 2.5
    if strict and 1 in answers and 2 in answers and 3 in answers:
        m = re.search(r"([\d.]+)\s*раз", answers[3].answer.lower())
        if m:
            claimed = float(m.group(1))
            nums = re.findall(r"([\d.]+)", answers[1].answer + " " + answers[2].answer)
            if len(nums) >= 2:
                actual = float(nums[1]) / float(nums[0]) if float(nums[0]) else 0
                if actual and abs(claimed - actual) / actual > 0.15:
                    issues.append(f"sq3: ratio {claimed} не сходится с {actual:.2f}")
                    rework.append(3)

    if strict:
        if any(w in q for w in ("инфляц", "ипц", "реальн")) and "get_inflation" not in plan_tools:
            issues.append("план не покрывает инфляцию")
        if any(w in q for w in ("разниц", "во сколько", "отношение")) and "calculate" not in plan_tools:
            issues.append("план без calculate для арифметики")

    if issues:
        action = "replan" if "план не покрывает" in " ".join(issues) else "rework"
        return Verdict(
            ok=False,
            reason="; ".join(dict.fromkeys(issues)),
            action=action,
            rework_ids=sorted(set(rework)) or [1],
        )
    return Verdict(ok=True, reason="правила пройдены", action="accept", rework_ids=[])


def critic(
    question: str,
    plan: Plan,
    answers: dict[int, WorkerAnswer],
    *,
    temperature: float = 0.7,
) -> Verdict:
    plan_lines = []
    for sq in plan.subquestions:
        tools = ",".join(sq.expected_tools) or "—"
        deps = f" depends_on={sq.depends_on}" if sq.depends_on else ""
        plan_lines.append(f"  {sq.id}. [{tools}]{deps}  «{sq.question}»")
    plan_text = "\n".join(plan_lines) or "  (пустой план)"

    ans_lines = []
    for sq_id in sorted(answers):
        a = answers[sq_id]
        tools = ",".join(a.used_tools) or "—"
        ans_lines.append(f"  {sq_id}. [{tools}] {a.answer}")
    answers_text = "\n".join(ans_lines) or "(ответов нет)"

    client = make_client()
    return client.chat.completions.create(
        model=get_model(),
        messages=[
            {
                "role": "system",
                "content": CRITIC_PROMPT.format(
                    question=question, plan_text=plan_text, answers_text=answers_text
                ),
            }
        ],
        response_model=Verdict,
        temperature=temperature,
        max_retries=2,
    )
