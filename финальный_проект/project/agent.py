"""ReAct-агент с инструментами (шаг 2)."""

from __future__ import annotations

import json
import time
from json.decoder import JSONDecodeError
from typing import Any

from llm_client import get_model, make_raw_client
from prompts import AGENT_SYSTEM, ANSWER_SYSTEM
from schema import Answer
from tools import TOOL_SCHEMAS, exec_tool, get_stats, reset_stats

MAX_STEPS = 6


def _estimate_tokens(messages: list[dict]) -> int:
    return sum(len(str(m.get("content", ""))) // 3 for m in messages)


def run_agent(
    question: str,
    *,
    initial_hits: dict | None = None,
    question_type: str = "lookup",
    verbose: bool = False,
) -> tuple[Answer, list[dict], dict]:
    reset_stats()
    t0 = time.perf_counter()
    trace: list[dict] = []

    if question_type == "negative":
        answer = Answer(
            question=question,
            speakers=[],
            summary="В корпусе интервью нет информации по этой теме.",
            citations=[],
            confidence=0.9,
            found_in_corpus=False,
            chunk_ids=initial_hits["ids"][0] if initial_hits else [],
        )
        stats = get_stats()
        path = {
            "retrieval_calls": stats["retrieval_calls"] + (1 if initial_hits else 0),
            "agent_steps": 0,
            "tools_used": stats["tools_used"],
            "chunks_read": stats["chunks_read"] + (len(initial_hits["ids"][0]) if initial_hits else 0),
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "latency_sec": round(time.perf_counter() - t0, 3),
        }
        return answer, trace, path

    raw = make_raw_client()
    model = get_model()
    messages: list[dict] = [{"role": "system", "content": AGENT_SYSTEM}]

    ctx = ""
    if initial_hits:
        parts = []
        for cid, doc in zip(initial_hits["ids"][0], initial_hits["documents"][0]):
            parts.append(f"[{cid}]\n{doc[:500]}")
        ctx = "\n\n---\n\n".join(parts)

    user = f"Вопрос: {question}\nТип: {question_type}"
    if question_type == "multi_hop":
        user += (
            "\n\nДля multi-hop: вызови grep_corpus по ключевым терминам, "
            "затем search_kb 2+ раза с разными запросами, собери ВСЕХ спикеров."
        )
    if ctx:
        user += f"\n\nПредварительный RAG-контекст:\n{ctx}"
    messages.append({"role": "user", "content": user})

    prompt_tok = 0
    completion_tok = 0

    for step in range(MAX_STEPS):
        resp = raw.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOL_SCHEMAS,
            temperature=0.1,
        )
        msg = resp.choices[0].message
        prompt_tok += getattr(resp.usage, "prompt_tokens", 0) or _estimate_tokens(messages)
        completion_tok += getattr(resp.usage, "completion_tokens", 0) or 50

        if msg.tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except JSONDecodeError:
                    args = {}
                obs = exec_tool(tc.function.name, args)
                trace.append({"step": step, "tool": tc.function.name, "args": args, "obs": obs})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(obs, ensure_ascii=False)[:4000],
                    }
                )
            if verbose:
                print(f"  [agent step {step}] tools: {[t.function.name for t in msg.tool_calls]}")
            continue

        # Финальный structured answer
        messages.append({"role": "assistant", "content": msg.content or ""})
        break

    # Structured synthesis
    from llm_client import make_client

    client = make_client()
    synth_ctx = "\n".join(
        json.dumps(t.get("obs"), ensure_ascii=False)[:800] for t in trace if "obs" in t
    )
    if ctx:
        synth_ctx = ctx + "\n" + synth_ctx

    answer: Answer = client.chat.completions.create(
        model=model,
        response_model=Answer,
        max_retries=3,
        temperature=0.1,
        messages=[
            {"role": "system", "content": ANSWER_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Вопрос: {question}\nКонтекст:\n{synth_ctx[:12000]}\n"
                    "Если ответа нет в контексте — found_in_corpus=false."
                ),
            },
        ],
    )
    answer.question = question

    stats = get_stats()
    path = {
        "retrieval_calls": stats["retrieval_calls"] + (1 if initial_hits else 0),
        "agent_steps": len(trace) + 1,
        "tools_used": stats["tools_used"],
        "chunks_read": stats["chunks_read"] + (len(initial_hits["ids"][0]) if initial_hits else 0),
        "prompt_tokens": prompt_tok,
        "completion_tokens": completion_tok,
        "latency_sec": round(time.perf_counter() - t0, 3),
    }
    return answer, trace, path
