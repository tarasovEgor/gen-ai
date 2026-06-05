"""
Раунд 2.5 — Autodiscovery аспектов (критерий «отлично»)
========================================================
Стадия A: модель сама выявляет темы из отзывов.
Стадия B: классификация по найденным темам (aspect: str, не Literal).
Сравнение с фиксированным раундом 2 (aspects.json).

Запуск:
    python aspect_discovery.py
    python aspect_discovery.py input/reviews.txt
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Type, TypeVar

import re

from openai import RateLimitError
from llm_client import get_model, make_client
from prompts import ASPECTS_SYSTEM, DISCOVER_SYSTEM
from schema import (
    REVIEW_ASPECTS,
    DiscoveredAspects,
    DynamicReviewSentiment,
)

REVIEW_SPLIT_RE = re.compile(r"═══ ОТЗЫВ \d+ ═══")


def split_by_review(text: str) -> list[str]:
    markers = REVIEW_SPLIT_RE.findall(text)
    parts = REVIEW_SPLIT_RE.split(text)
    _, *chunks = parts
    return [
        (m + b).strip()
        for m, b in zip(markers, chunks)
        if (m + b).strip()
    ] or [text]

client = make_client()
MODEL = get_model()
OUT = Path(__file__).parent / "output"

T = TypeVar("T")


def _call(model_type: Type[T], system: str, user: str, retries: int = 10) -> T:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            return client.chat.completions.create(
                model=MODEL,
                response_model=model_type,
                max_retries=3,
                temperature=0.0,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
        except RateLimitError as e:
            last_err = e
            wait = min(2 ** attempt + 1, 120)
            print(f"  [rate limit] пауза {wait}с...", flush=True)
            time.sleep(wait)
    assert last_err is not None
    raise last_err


def load_text(path: str) -> str:
    p = Path(path)
    if p.is_dir():
        return "\n\n".join(f.read_text(encoding="utf-8") for f in sorted(p.glob("*.txt")))
    return p.read_text(encoding="utf-8")


def discover_aspects(text: str) -> DiscoveredAspects:
    return _call(DiscoveredAspects, DISCOVER_SYSTEM, text)


def extract_with_discovered(
    text: str,
    discovered: DiscoveredAspects,
) -> list[DynamicReviewSentiment]:
    dynamic_block = "\n".join(
        f"- {a.name}: {a.description}" for a in discovered.aspects
    )
    sys_prompt = ASPECTS_SYSTEM + (
        "\n\nИспользуй СТРОГО эти аспекты (поле aspect = name):\n" + dynamic_block
    )
    return _call(list[DynamicReviewSentiment], sys_prompt, text)


def compare(fixed_path: Path, dynamic: list[DynamicReviewSentiment]) -> dict:
    fixed = json.loads(fixed_path.read_text(encoding="utf-8"))
    fixed_used = {a["aspect"] for p in fixed for a in p["aspects"]}
    dyn_used = {a.aspect for p in dynamic for p_aspects in [p.aspects] for a in p_aspects}
    discovered_names = {a.aspect for p in dynamic for a in p.aspects}

    # Темы из autodiscovery, которых нет в Literal
    invented = discovered_names - set(REVIEW_ASPECTS)
    # Literal-темы, которые не встретились ни в fixed, ни в dynamic
    literal_unused = set(REVIEW_ASPECTS) - fixed_used
    # Новые по сравнению с fixed (использованные в dynamic, но не в fixed)
    new_vs_fixed = dyn_used - fixed_used
    missing_in_dynamic = fixed_used - dyn_used

    return {
        "fixed_literal_used": sorted(fixed_used),
        "dynamic_used": sorted(dyn_used),
        "discovered_all": sorted(discovered_names),
        "invented_not_in_literal": sorted(invented),
        "new_vs_fixed": sorted(new_vs_fixed),
        "literal_unused_in_fixed": sorted(literal_unused),
        "missing_in_dynamic": sorted(missing_in_dynamic),
        "fixed_count": len(fixed_used),
        "dynamic_count": len(dyn_used),
    }


def main() -> None:
    if "--offline" in sys.argv:
        from build_discovery_offline import main as offline_main

        offline_main()
        return

    input_path = sys.argv[1] if len(sys.argv) > 1 else "input/reviews.txt"
    text = load_text(input_path)
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    print("━━━ Стадия A: autodiscovery тем ━━━", flush=True)
    discovered = discover_aspects(text)
    (OUT / "discovered_aspects.json").write_text(
        discovered.model_dump_json(indent=2), encoding="utf-8"
    )
    print(f"Найдено тем: {len(discovered.aspects)}")
    for a in discovered.aspects:
        print(f"  • {a.name} — {a.description}")

    print("\n━━━ Стадия B: классификация по найденным темам (батчи по 10) ━━━", flush=True)
    chunks = split_by_review(text)
    dynamic: list[DynamicReviewSentiment] = []
    for i in range(0, len(chunks), 10):
        batch = "\n\n".join(chunks[i : i + 10])
        batch_result = extract_with_discovered(batch, discovered)
        dynamic.extend(batch_result)
        print(f"  батч {i // 10 + 1}: +{len(batch_result)} авторов", flush=True)
        if i + 10 < len(chunks):
            time.sleep(2)
    (OUT / "aspects_discovered.json").write_text(
        json.dumps([p.model_dump() for p in dynamic], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    n_scores = sum(len(p.aspects) for p in dynamic)
    print(f"Оценок: {n_scores} по {len(dynamic)} авторам")

    fixed_path = OUT / "aspects.json"
    if fixed_path.exists():
        cmp = compare(fixed_path, dynamic)
        (OUT / "aspect_comparison.json").write_text(
            json.dumps(cmp, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("\n━━━ Сравнение с раундом 2 (фиксированный Literal) ━━━")
        print(f"  Literal использовано:  {cmp['fixed_count']} → {cmp['fixed_literal_used']}")
        print(f"  Dynamic использовано:  {cmp['dynamic_count']} → {cmp['dynamic_used']}")
        if cmp["invented_not_in_literal"]:
            print(f"  ⊕ придуманы моделью (нет в Literal): {cmp['invented_not_in_literal']}")
        if cmp["new_vs_fixed"]:
            print(f"  ⊕ новые vs fixed-run:              {cmp['new_vs_fixed']}")
        if cmp["missing_in_dynamic"]:
            print(f"  ⊖ есть в fixed, нет в dynamic:     {cmp['missing_in_dynamic']}")
        if cmp["literal_unused_in_fixed"]:
            print(f"  ⊖ Literal не обсуждали (fixed):    {cmp['literal_unused_in_fixed']}")

    print(f"\nВремя: {time.time() - t0:.1f}с")
    print("Сохранено: output/discovered_aspects.json, aspects_discovered.json, aspect_comparison.json")


if __name__ == "__main__":
    main()
