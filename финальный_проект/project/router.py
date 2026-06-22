"""Router: классификация типа вопроса (мультиагент, шаг 1)."""

from __future__ import annotations

from llm_client import get_model, make_client
from prompts import ROUTER_SYSTEM
from schema import RouterDecision

NEGATIVE_HINTS = ("блокчейн", "nft", "криптовалют", "метаверс", "web3")
MULTI_HINTS = ("одновременно", "и на", "и кач", "сбп", "нескольк", "все три", "оба")


def route(question: str) -> RouterDecision:
    q = question.lower()
    if any(h in q for h in NEGATIVE_HINTS):
        return RouterDecision(
            question_type="negative",
            reasoning="ключевые слова вне домена корпуса",
            retrieval_k=4,
        )

    if any(h in q for h in MULTI_HINTS) or question.count(" и ") >= 2:
        return RouterDecision(
            question_type="multi_hop",
            reasoning="составной вопрос / несколько тем",
            retrieval_k=12,
        )

    client = make_client()
    dec: RouterDecision = client.chat.completions.create(
        model=get_model(),
        response_model=RouterDecision,
        max_retries=2,
        temperature=0.0,
        messages=[
            {"role": "system", "content": ROUTER_SYSTEM},
            {"role": "user", "content": question},
        ],
    )
    if dec.question_type == "multi_hop" and dec.retrieval_k < 10:
        dec.retrieval_k = 12
    elif dec.question_type == "lookup" and dec.retrieval_k < 6:
        dec.retrieval_k = 6
    return dec
