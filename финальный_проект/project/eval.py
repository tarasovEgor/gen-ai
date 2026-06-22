"""
Eval: ≥18 вопросов × метрики правильности и пути.

  python eval.py
  python eval.py --ids 1,3,13
  python eval.py --retrieval-only   # быстрый smoke без LLM-агента
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from pipeline import analyze
from rag import ensure_index, hybrid_retrieve
from retry_util import with_retry

GOLD_PATH = Path(__file__).parent / "input" / "gold.json"
OUT_PATH = Path(__file__).parent / "output" / "eval_results.json"
OUT_RETRIEVAL = Path(__file__).parent / "output" / "eval_retrieval_only.json"


def load_gold() -> list[dict]:
    return json.loads(GOLD_PATH.read_text(encoding="utf-8"))


def source_recall(retrieved: list[str], gold: list[str]) -> float:
    if not gold:
        return 1.0
    rs = set(retrieved)
    found = sum(1 for g in gold if g in rs)
    return found / len(gold)


def retrieval_recall(question: str, gold: list[str], k: int = 5) -> dict:
    hits = hybrid_retrieve(question, k=k)
    sources = list({rid.split("__")[0] for rid in hits["ids"][0]})
    return {
        "retrieved_sources": sources,
        "source_recall": source_recall(sources, gold),
    }


def eval_one(item: dict, *, retrieval_only: bool = False) -> dict:
    q = item["question"]
    gold = item.get("gold_sources", [])
    expect_neg = item.get("expect_negative", False)

    if retrieval_only:
        rr = retrieval_recall(q, gold)
        passed = (rr["source_recall"] >= 0.5) if gold else True
        return {
            "id": item["id"],
            "type": item["type"],
            "question": q,
            "mode": "retrieval_only",
            "source_recall": rr["source_recall"],
            "retrieved_sources": rr["retrieved_sources"],
            "pass": passed,
            "path": {"retrieval_calls": 1, "agent_steps": 0, "tools_used": []},
        }

    result = with_retry(
        lambda: analyze(
            q,
            verbose=False,
            gold_sources=gold or None,
            expect_negative=expect_neg,
        )
    )
    ans = result.answer
    ghosts = result.judge.ghost_citations

    # Спикеры → doc_id через retrieved + citations
    cited_docs = {c.doc_id.split("__")[0] for c in ans.citations}
    all_found = set(result.retrieved_sources) | cited_docs

    if expect_neg:
        correct = not ans.found_in_corpus
        src_rec = 1.0 if correct else 0.0
    else:
        src_rec = source_recall(list(all_found), gold)
        correct = src_rec >= 0.5 and ans.found_in_corpus

    judge_ok = result.judge.overall == "pass"
    passed = correct and judge_ok and ghosts == 0

    return {
        "id": item["id"],
        "type": item["type"],
        "question": q,
        "mode": "full",
        "source_recall": round(src_rec, 3),
        "retrieved_sources": result.retrieved_sources,
        "cited_docs": sorted(cited_docs),
        "speakers": ans.speakers,
        "found_in_corpus": ans.found_in_corpus,
        "judge": result.judge.overall,
        "ghost_citations": ghosts,
        "pass": passed,
        "summary_preview": ans.summary[:120],
        "path": result.path.model_dump(),
        "gold_sources": gold,
        "expect_negative": expect_neg,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", type=str, default="", help="1,2,3")
    ap.add_argument("--retrieval-only", action="store_true")
    ap.add_argument("--force", action="store_true", help="перезапустить даже если id уже в файле")
    ap.add_argument("--pause", type=float, default=2.0)
    args = ap.parse_args()

    ensure_index()
    gold = load_gold()
    if args.ids.strip():
        wanted = {int(x) for x in args.ids.split(",")}
        gold = [g for g in gold if g["id"] in wanted]

    out_file = OUT_RETRIEVAL if args.retrieval_only else OUT_PATH

    results: list[dict] = []
    if out_file.exists():
        try:
            results = json.loads(out_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            results = []
    done = {r["id"] for r in results}

    print(f"Eval: {len(gold)} кейсов{' [retrieval-only]' if args.retrieval_only else ''}\n")
    t0 = time.perf_counter()

    for item in gold:
        if item["id"] in done and not args.force:
            print(f"  [{item['id']:2d}] skip (уже в файле)")
            continue
        print(f"  [{item['id']:2d}] {item['type']}: {item['question'][:50]}...")
        try:
            row = eval_one(item, retrieval_only=args.retrieval_only)
        except Exception as e:
            row = {
                "id": item["id"],
                "type": item["type"],
                "question": item["question"],
                "pass": False,
                "error": str(e),
            }
        results = [r for r in results if r["id"] != item["id"]] + [row]
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        mark = "✓" if row.get("pass") else "✗"
        print(f"       {mark} recall={row.get('source_recall', '—')} judge={row.get('judge', '—')}")
        if args.pause and not args.retrieval_only:
            time.sleep(args.pause)

    passed = sum(1 for r in results if r.get("pass"))
    total = len(results)
    elapsed = time.perf_counter() - t0
    ghosts = sum(r.get("ghost_citations", 0) for r in results)

    print("\n" + "=" * 60)
    print(f"Pass-rate: {passed}/{total} ({passed / total:.0%})" if total else "—")
    print(f"Ghost-цитат всего: {ghosts}")
    print(f"Время: {elapsed:.1f}с")
    print(f"Сохранено: {out_file}")

    hall_path = out_file.parent / "hallucination_report.json"
    hall_path.write_text(
        json.dumps(
            {
                "total_ghost_citations": ghosts,
                "cases_with_ghosts": [r["id"] for r in results if r.get("ghost_citations", 0) > 0],
                "pass_rate": f"{passed}/{total}",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Ghost-report: {hall_path}")


if __name__ == "__main__":
    main()
