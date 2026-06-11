"""
Eval по gold.json. Метрика: hit-rate@5 на уровне документа-источника.

Сравнение двух стратегий чанкинга:
    python eval.py                  # обе стратегии
    python eval.py --strategy fixed # только fixed
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline import collection_name, get_collection, ingest, retrieve

GOLD_PATH = Path(__file__).parent / "data" / "gold.json"
RESULTS_PATH = Path(__file__).parent / "output" / "eval_results.json"


def load_gold() -> list[dict]:
    return json.loads(GOLD_PATH.read_text(encoding="utf-8"))


def hit_rate(retrieved_ids: list[str], gold_sources: list[str]) -> float:
    retrieved_sources = {rid.split("__")[0] for rid in retrieved_ids}
    found = [g for g in gold_sources if g in retrieved_sources]
    return len(found) / len(gold_sources)


def run(strategy: str, k: int = 5, verbose: bool = True) -> dict:
    coll = get_collection(strategy)
    if coll.count() == 0:
        print(f"Коллекция {collection_name(strategy)} пуста — индексирую...")
        ingest(strategy)

    gold = load_gold()
    total = 0.0
    results = []

    label = "FIXED (2000 символов)" if strategy == "fixed" else "RECURSIVE (400/80)"
    if verbose:
        print(f"\n=== {label} ===\n")

    for item in gold:
        hits = retrieve(strategy, item["question"], k=k)
        retrieved_ids = hits["ids"][0]
        retrieved_sources = [rid.split("__")[0] for rid in retrieved_ids]
        score = hit_rate(retrieved_ids, item["gold_sources"])
        total += score
        results.append(
            {
                "id": item["id"],
                "type": item["type"],
                "question": item["question"],
                "score": score,
                "gold": item["gold_sources"],
                "retrieved_sources": retrieved_sources,
                "retrieved_ids": retrieved_ids,
            }
        )
        if verbose:
            mark = "✓" if score == 1.0 else ("◐" if score > 0 else "✗")
            hard = " [сложный]" if item.get("hard") else ""
            print(
                f"  [{item['id']:2d}] {item['type']:12s}  "
                f"hit@{k}={score:.2f}  {mark}{hard}  {item['question'][:55]}"
            )

    mean = total / len(gold)
    if verbose:
        print(f"\n  ИТОГО: hit-rate@{k} = {mean:.2f}  ({total:.1f} / {len(gold)})")
    return {"strategy": strategy, "k": k, "mean": mean, "results": results}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=["fixed", "recursive", "both"], default="both")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    strategies = ["fixed", "recursive"] if args.strategy == "both" else [args.strategy]
    all_results = {}
    for s in strategies:
        all_results[s] = run(s, k=args.k, verbose=not args.quiet)

    if len(strategies) == 2 and not args.quiet:
        f = all_results["fixed"]["mean"]
        r = all_results["recursive"]["mean"]
        winner = "recursive" if r >= f else "fixed"
        print(f"\n{'='*40}")
        print(f"  fixed:     hit-rate@{args.k} = {f:.2f}")
        print(f"  recursive: hit-rate@{args.k} = {r:.2f}")
        print(f"  победитель: {winner} (+{abs(r-f):.2f})")

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if not args.quiet:
        print(f"\nСохранено: {RESULTS_PATH}")


if __name__ == "__main__":
    main()
