"""
pipeline.py — конвейер анализа отзывов: IE → аспекты → Map-Reduce → judge.

Запуск:
    python pipeline.py
    python pipeline.py input/reviews.txt output
"""

from __future__ import annotations

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from openai import RateLimitError
from pydantic import ValidationError

from llm_client import get_model, make_client
from prompts import (
    ASPECTS_SYSTEM,
    CHUNK_SYSTEM,
    IE_SYSTEM,
    JUDGE_SYSTEM,
    REDUCE_SYSTEM,
)
from schema import (
    ASPECT_LABELS_RU,
    REVIEW_ASPECTS,
    ChunkSummary,
    JudgeReport,
    Review,
    ReviewSentiment,
    ReviewsSummary,
)

# Ограничение параллельных запросов к API (защита от 429)
_API_SEMAPHORE = threading.Semaphore(1)

client = make_client()
MODEL = get_model()

# Тарифы DeepSeek (примерные, USD за 1M токенов) — для оценки стоимости
_PRICE_INPUT_PER_1M = 0.27
_PRICE_OUTPUT_PER_1M = 1.10
_PRICE_CACHE_HIT_PER_1M = 0.07


@dataclass
class RunMetrics:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_hit_tokens: int = 0
    validation_errors: int = 0
    reviews_extracted: int = 0
    reviews_valid: int = 0
    ghost_quotes: list[tuple[str, str]] = field(default_factory=list)
    elapsed_sec: float = 0.0
    stages: dict = field(default_factory=dict)

    def add_usage(self, completion) -> None:
        u = getattr(completion, "usage", None)
        if not u:
            return
        self.input_tokens += getattr(u, "prompt_tokens", 0) or 0
        self.output_tokens += getattr(u, "completion_tokens", 0) or 0
        details = getattr(u, "prompt_tokens_details", None)
        if details:
            self.cache_hit_tokens += getattr(details, "cached_tokens", 0) or 0

    @property
    def cost_usd(self) -> float:
        billable_in = max(0, self.input_tokens - self.cache_hit_tokens)
        return (
            billable_in * _PRICE_INPUT_PER_1M / 1_000_000
            + self.cache_hit_tokens * _PRICE_CACHE_HIT_PER_1M / 1_000_000
            + self.output_tokens * _PRICE_OUTPUT_PER_1M / 1_000_000
        )


def _call(model_type, system: str, user: str, metrics: RunMetrics, api_retries: int = 8):
    last_err: Exception | None = None
    with _API_SEMAPHORE:
        for attempt in range(api_retries):
            try:
                result, resp = client.chat.completions.create(
                    model=MODEL,
                    response_model=model_type,
                    max_retries=3,
                    temperature=0.0,
                    with_completion=True,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )
                metrics.add_usage(resp)
                return result
            except RateLimitError as e:
                last_err = e
                wait = 2 ** attempt + 1
                print(f"  [rate limit] пауза {wait}с (попытка {attempt + 1}/{api_retries})...")
                time.sleep(wait)
    assert last_err is not None
    raise last_err


# ── Раунд 1: Information Extraction ──────────────────────
def _validate_reviews(raw: list[Review], metrics: RunMetrics) -> list[Review]:
    valid: list[Review] = []
    for item in raw:
        try:
            valid.append(Review.model_validate(item.model_dump()))
            metrics.reviews_valid += 1
        except ValidationError:
            metrics.validation_errors += 1
    return valid


def extract_reviews(text: str, metrics: RunMetrics) -> list[Review]:
    """IE одним запросом (для коротких батчей)."""
    raw = _call(list[Review], IE_SYSTEM, text, metrics)
    metrics.reviews_extracted += len(raw)
    return _validate_reviews(raw, metrics)


def extract_reviews_batched(
    text: str,
    metrics: RunMetrics,
    batch_size: int = 10,
) -> list[Review]:
    """IE батчами — меньше пропусков на длинных датасетах."""
    chunks = split_by_review(text)
    all_valid: list[Review] = []
    for i in range(0, len(chunks), batch_size):
        batch = "\n\n".join(chunks[i : i + batch_size])
        batch_valid = extract_reviews(batch, metrics)
        all_valid.extend(batch_valid)
        print(f"   IE батч {i // batch_size + 1}: +{len(batch_valid)} отзывов")
    return all_valid


# ── Раунд 2: Аспектный анализ ────────────────────────────
def extract_aspects(text: str, metrics: RunMetrics) -> list[ReviewSentiment]:
    return _call(list[ReviewSentiment], ASPECTS_SYSTEM, text, metrics)


def extract_aspects_batched(
    text: str,
    metrics: RunMetrics,
    batch_size: int = 10,
) -> list[ReviewSentiment]:
    chunks = split_by_review(text)
    all_aspects: list[ReviewSentiment] = []
    for i in range(0, len(chunks), batch_size):
        batch = "\n\n".join(chunks[i : i + batch_size])
        batch_aspects = extract_aspects(batch, metrics)
        all_aspects.extend(batch_aspects)
        print(f"   аспекты батч {i // batch_size + 1}: +{len(batch_aspects)} авторов")
    return all_aspects


def check_quotes(
    aspects: list[ReviewSentiment],
    source: str,
) -> list[tuple[str, str]]:
    """Sanity-check: цитаты, не найденные в исходном тексте (ghost quotes)."""
    src = source.lower()
    ghosts: list[tuple[str, str]] = []
    for r in aspects:
        for a in r.aspects:
            probe = a.quote.strip().lower()[:30]
            if probe and probe not in src:
                ghosts.append((r.author, a.quote))
    return ghosts


def build_heatmap(
    aspects: list[ReviewSentiment],
    out_path: str,
) -> None:
    authors = [r.author for r in aspects]
    sent_map = {"positive": 1, "negative": -1, "neutral": 0}
    matrix = np.full((len(authors), len(REVIEW_ASPECTS)), np.nan)
    for i, r in enumerate(aspects):
        for a in r.aspects:
            if a.aspect in REVIEW_ASPECTS:
                j = REVIEW_ASPECTS.index(a.aspect)
                matrix[i, j] = sent_map[a.sentiment]
    plt.figure(figsize=(10, 12))
    sns.heatmap(
        matrix,
        annot=True,
        fmt=".0f",
        xticklabels=[ASPECT_LABELS_RU.get(a, a) for a in REVIEW_ASPECTS],
        yticklabels=authors,
        center=0,
        cmap="RdYlGn",
        cbar_kws={"label": "sentiment"},
    )
    plt.title("Аспектная тональность по отзывам «МойБанк»")
    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    plt.close()


# ── Раунд 3: Map-Reduce ──────────────────────────────────
REVIEW_SPLIT_RE = re.compile(r"═══ ОТЗЫВ \d+ ═══")


def split_by_review(text: str) -> list[str]:
    """Разбить сводный файл на отдельные отзывы для MAP-фазы."""
    parts = REVIEW_SPLIT_RE.split(text)
    header, *chunks = parts
    result = []
    markers = REVIEW_SPLIT_RE.findall(text)
    for marker, body in zip(markers, chunks):
        chunk = marker + body
        if chunk.strip():
            result.append(chunk.strip())
    if not result:
        result = [text]
    return result


def summarize_chunk(chunk: str, metrics: RunMetrics) -> ChunkSummary:
    return _call(ChunkSummary, CHUNK_SYSTEM, chunk, metrics)


def reduce_summaries(
    summaries: list[ChunkSummary],
    metrics: RunMetrics,
    reduce_prompt: str = REDUCE_SYSTEM,
) -> ReviewsSummary:
    joined = "\n\n".join(
        f"## {s.speaker} ({s.sentiment})\n" + "\n".join(f"- {p}" for p in s.key_points)
        for s in summaries
    )
    return _call(ReviewsSummary, reduce_prompt, joined, metrics)


def summarize_reviews(
    text: str,
    metrics: RunMetrics,
    workers: int = 4,
    reduce_prompt: str = REDUCE_SYSTEM,
    chunk_delay: float = 1.0,
) -> ReviewsSummary:
    chunks = split_by_review(text)
    n = len(chunks)
    print(
        f"  [MR] MAP: {n} отзывов, ThreadPoolExecutor(max_workers={workers})...",
        flush=True,
    )
    t0 = time.time()
    buf: list[ChunkSummary | None] = [None] * n

    def _map_with_delay(idx: int, chunk: str) -> tuple[int, ChunkSummary]:
        if idx > 0:
            time.sleep(chunk_delay)
        return idx, summarize_chunk(chunk, metrics)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_map_with_delay, i, c) for i, c in enumerate(chunks)]
        done = 0
        for fut in as_completed(futures):
            i, summary = fut.result()
            buf[i] = summary
            done += 1
            if done % 10 == 0 or done == n:
                print(f"  [MR] {done}/{n} готов ({time.time() - t0:.1f}с)", flush=True)
    summaries = [s for s in buf if s]

    print(f"  [MR] MAP {time.time() - t0:.1f}с → REDUCE...")
    result = reduce_summaries(summaries, metrics, reduce_prompt)
    print(f"  [MR] всего {time.time() - t0:.1f}с")
    return result


# ── Раунд 5: LLM-as-judge ────────────────────────────────
def build_evidence_packet(reviews: list[dict], summary: dict) -> str:
    parts = ["## Рекомендации (которые оцениваем)"]
    for i, a in enumerate(summary.get("action_items", []), 1):
        parts.append(f"  {i}. {a}")
    parts.append("\n## Проблемы из отзывов (исходные данные)")
    for r in reviews:
        for issue in r.get("issues", []):
            parts.append(
                f"  - [{r['author']}/{issue['category']}, sev={issue['severity']}] "
                f"«{issue['quote']}»"
            )
    return "\n".join(parts)


def judge(reviews: list[dict], summary: dict, metrics: RunMetrics) -> JudgeReport:
    """LLM-as-judge: оценка обоснованности action_items."""
    evidence = build_evidence_packet(reviews, summary)
    return _call(JudgeReport, JUDGE_SYSTEM, evidence, metrics)


# Улучшенный REDUCE-промпт (если judge score < 0.7)
REDUCE_SYSTEM_STRICT = REDUCE_SYSTEM + """

Дополнительные требования:
- Каждая рекомендация должна напрямую отвечать на конкретную жалобу из отзывов.
- Не предлагай фичи, о которых пользователи не жаловались.
- Избегай общих фраз вроде «улучшить UX» без привязки к жалобе."""


def load_input(input_path: str) -> str:
    p = Path(input_path)
    if p.is_dir():
        texts = []
        for f in sorted(p.glob("*.txt")):
            texts.append(f.read_text(encoding="utf-8"))
        return "\n\n".join(texts)
    return p.read_text(encoding="utf-8")


def _default_out_dir(input_path: str) -> Path:
    p = Path(input_path)
    base = Path(__file__).parent
    if p.is_dir():
        return base / "output"
    return base / "output"


def analyze(input_path: str, *, skip_ie: bool = False) -> RunMetrics:
    """Полный конвейер: IE → аспекты → Map-Reduce → judge."""
    t_start = time.time()
    metrics = RunMetrics()
    out = _default_out_dir(input_path)
    out.mkdir(parents=True, exist_ok=True)

    text = load_input(input_path)
    n_input = len(split_by_review(text))
    print(f"Загружено: {len(text)} символов, {n_input} отзывов из {input_path}", flush=True)

    reviews_path = out / "reviews.json"
    aspects_path = out / "aspects.json"

    if skip_ie and reviews_path.exists() and aspects_path.exists():
        print("→ Акт 1-2: загрузка reviews.json + aspects.json...", flush=True)
        reviews_data = json.loads(reviews_path.read_text(encoding="utf-8"))
        reviews = [Review.model_validate(r) for r in reviews_data]
        metrics.reviews_valid = len(reviews)
        metrics.reviews_extracted = len(reviews)
        n_issues = sum(len(r.issues) for r in reviews)
        aspects_data = json.loads(aspects_path.read_text(encoding="utf-8"))
        aspects = [ReviewSentiment.model_validate(a) for a in aspects_data]
        ghosts = check_quotes(aspects, text)
        metrics.ghost_quotes = ghosts
        total_quotes = sum(len(r.aspects) for r in aspects)
        ghost_pct = len(ghosts) / total_quotes * 100 if total_quotes else 0
        print(
            f"   {len(reviews)}/{n_input} отзывов, {n_issues} проблем; "
            f"ghost: {len(ghosts)} ({ghost_pct:.1f}%)",
            flush=True,
        )
    else:
        # Акт 1: IE (батчами по 10)
        print("→ Акт 1: extract_reviews (IE, батчи по 10)...", flush=True)
        t0 = time.time()
        reviews = extract_reviews_batched(text, metrics, batch_size=10)
        reviews_data = [r.model_dump(mode="json") for r in reviews]
        reviews_path.write_text(
            json.dumps(reviews_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        metrics.stages["ie_sec"] = time.time() - t0
        n_issues = sum(len(r.issues) for r in reviews)
        print(
            f"   {metrics.reviews_valid}/{n_input} валидных отзывов "
            f"({metrics.validation_errors} ValidationError), {n_issues} проблем",
            flush=True,
        )

        # Акт 2: Аспекты (батчами)
        print("→ Акт 2: extract_aspects (батчи по 10)...", flush=True)
        t0 = time.time()
        aspects = extract_aspects_batched(text, metrics, batch_size=10)
        ghosts = check_quotes(aspects, text)
        metrics.ghost_quotes = ghosts
        metrics.stages["aspects_sec"] = time.time() - t0
        total_quotes = sum(len(r.aspects) for r in aspects)
        ghost_pct = len(ghosts) / total_quotes * 100 if total_quotes else 0
        print(
            f"   {len(aspects)} авторов, {total_quotes} оценок, "
            f"ghost: {len(ghosts)} ({ghost_pct:.1f}%)",
            flush=True,
        )

        build_heatmap(aspects, str(out / "heatmap.png"))
        aspects_data = [a.model_dump() for a in aspects]
        aspects_path.write_text(
            json.dumps(aspects_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # Акт 3: Map-Reduce
    print("→ Акт 3: summarize_reviews (Map-Reduce)...")
    t0 = time.time()
    summary = summarize_reviews(text, metrics)
    metrics.stages["mr_sec"] = time.time() - t0
    (out / "summary.json").write_text(
        summary.model_dump_json(indent=2),
        encoding="utf-8",
    )

    # Акт 5: Judge
    print("→ Акт 5: judge...")
    t0 = time.time()
    summary_dict = json.loads(summary.model_dump_json())
    report = judge(reviews_data, summary_dict, metrics)
    metrics.stages["judge_sec"] = time.time() - t0

    if report.overall_score < 0.7:
        print(f"   overall_score={report.overall_score:.2f} < 0.7 — перезапуск REDUCE...")
        t0 = time.time()
        summary = summarize_reviews(text, metrics, reduce_prompt=REDUCE_SYSTEM_STRICT)
        metrics.stages["mr_retry_sec"] = time.time() - t0
        (out / "summary.json").write_text(
            summary.model_dump_json(indent=2),
            encoding="utf-8",
        )
        summary_dict = json.loads(summary.model_dump_json())
        report = judge(reviews_data, summary_dict, metrics)

    (out / "judge_report.json").write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )

    metrics.elapsed_sec = time.time() - t_start
    run_stats = {
        "reviews_input": n_input,
        "reviews_valid": metrics.reviews_valid,
        "validation_errors": metrics.validation_errors,
        "issues_total": n_issues,
        "ghost_quotes": len(ghosts),
        "ghost_quote_pct": round(ghost_pct, 1),
        "ghost_details": [{"author": a, "quote": q} for a, q in ghosts],
        "overall_score": report.overall_score,
        "elapsed_sec": round(metrics.elapsed_sec, 1),
        "input_tokens": metrics.input_tokens,
        "output_tokens": metrics.output_tokens,
        "cache_hit_tokens": metrics.cache_hit_tokens,
        "cost_usd": round(metrics.cost_usd, 4),
        "stages_sec": metrics.stages,
    }
    (out / "run_metrics.json").write_text(
        json.dumps(run_stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n=== ИТОГ ===")
    print(summary.headline)
    print("\nКлючевые выводы:")
    for kf in summary.key_findings:
        print(f"  • {kf}")
    print("\nРекомендации:")
    for ai in summary.action_items:
        print(f"  → {ai}")
    print(f"\nоценка судьи: {report.overall_score:.2f}")
    print(f"ghost-цитат: {len(ghosts)} ({ghost_pct:.1f}%)")
    print(f"время: {metrics.elapsed_sec:.1f}с, стоимость: ${metrics.cost_usd:.4f}")
    print(f"\nВсе артефакты в: {out}/")
    return metrics


def main() -> None:
    import sys

    input_path = sys.argv[1] if len(sys.argv) > 1 else "input/reviews.txt"
    skip_ie = "--skip-ie" in sys.argv
    analyze(input_path, skip_ie=skip_ie)


if __name__ == "__main__":
    main()
