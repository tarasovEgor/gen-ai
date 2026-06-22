"""LLM-as-judge: groundedness ответа."""

from __future__ import annotations

from llm_client import get_model, make_client
from prompts import JUDGE_SYSTEM
from schema import Answer, JudgeReport


def judge_answer(
    question: str,
    answer: Answer,
    *,
    gold_sources: list[str] | None = None,
    expect_negative: bool = False,
    ghost_count: int = 0,
) -> JudgeReport:
    gold_note = ""
    if expect_negative:
        gold_note = "Ожидается: данных в корпусе НЕТ (found_in_corpus=false)."
    elif gold_sources:
        gold_note = f"Ожидаемые документы-источники: {', '.join(gold_sources)}"

    ctx = (
        f"Вопрос: {question}\n"
        f"Ответ: {answer.summary}\n"
        f"Спикеры: {answer.speakers}\n"
        f"found_in_corpus: {answer.found_in_corpus}\n"
        f"Цитаты: {[c.quote[:80] for c in answer.citations]}\n"
        f"Ghost-цитат (детерминированная проверка): {ghost_count}\n"
        f"{gold_note}"
    )

    client = make_client()
    report: JudgeReport = client.chat.completions.create(
        model=get_model(),
        response_model=JudgeReport,
        max_retries=2,
        temperature=0.0,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": ctx},
        ],
    )
    report.ghost_citations = ghost_count
    if ghost_count > 0:
        report.overall = "fail"
    return report
