"""
CloudPay Knowledge Assistant — единая точка входа.

  python pipeline.py --ingest
  python pipeline.py --question "Кто жаловался на webhook?"
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from agent import run_agent
from hallucination import check_citations, snap_citations
from judge import judge_answer
from rag import ensure_index, hybrid_retrieve, ingest
from router import route
from schema import PathMetrics, PipelineResult

OUTPUT_DIR = Path(__file__).parent / "output"
TRACE_PATH = OUTPUT_DIR / "trace.jsonl"


def _append_trace(entry: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    row = {"ts": datetime.now().isoformat(timespec="seconds"), **entry}
    with TRACE_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def analyze(
    question: str,
    *,
    verbose: bool = True,
    gold_sources: list[str] | None = None,
    expect_negative: bool = False,
) -> PipelineResult:
    ensure_index()
    t0 = time.perf_counter()

    router_dec = route(question)
    if verbose:
        print(f"[router] {router_dec.question_type}, k={router_dec.retrieval_k}")

    hits = hybrid_retrieve(question, k=router_dec.retrieval_k)
    retrieved_sources = list({rid.split("__")[0] for rid in hits["ids"][0]})

    answer, trace, path_dict = run_agent(
        question,
        initial_hits=hits,
        question_type=router_dec.question_type,
        verbose=verbose,
    )
    answer.chunk_ids = hits["ids"][0]
    answer.citations = snap_citations(answer.citations)

    chunk_texts = hits["documents"][0]
    ghosts = check_citations(answer.citations, chunk_texts)
    judge_report = judge_answer(
        question,
        answer,
        gold_sources=gold_sources,
        expect_negative=expect_negative or router_dec.question_type == "negative",
        ghost_count=len(ghosts),
    )

    path = PathMetrics(**path_dict)
    path.latency_sec = round(time.perf_counter() - t0, 3)

    result = PipelineResult(
        question=question,
        router=router_dec,
        answer=answer,
        judge=judge_report,
        path=path,
        retrieved_sources=retrieved_sources,
        trace=trace,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "last_result.json"
    payload = result.model_dump()
    payload["ghosts"] = ghosts
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    _append_trace(
        {
            "question": question[:120],
            "type": router_dec.question_type,
            "pass_judge": judge_report.overall,
            "ghosts": len(ghosts),
            "sources": retrieved_sources,
            "tools": path.tools_used,
            "steps": path.agent_steps,
            "tokens_in": path.prompt_tokens,
            "tokens_out": path.completion_tokens,
            "latency_sec": path.latency_sec,
        }
    )

    if verbose:
        print(f"\nОтвет: {answer.summary[:200]}...")
        print(f"Спикеры: {answer.speakers}")
        print(f"Judge: {judge_report.overall}, ghosts={len(ghosts)}")
        print(f"Path: {path.agent_steps} steps, tools={path.tools_used}, {path.latency_sec}s")
        print(f"Сохранено: {out_path}")

    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingest", action="store_true", help="Построить Chroma-индекс")
    ap.add_argument("--question", "-q", type=str, default="")
    args = ap.parse_args()

    if args.ingest:
        ingest()
        return
    if not args.question:
        ap.error("Укажи --question или --ingest")
    analyze(args.question)


if __name__ == "__main__":
    main()
