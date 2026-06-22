"""Проверка и исправление ghost-цитат."""

from __future__ import annotations

import re
from pathlib import Path

from schema import Citation

CORPUS_DIR = Path(__file__).parent / "input" / "corpus"
_cache: dict[str, str] = {}


def _doc_text(doc_id: str) -> str:
    stem = doc_id.split("__")[0]
    if stem not in _cache:
        path = CORPUS_DIR / f"{stem}.txt"
        _cache[stem] = path.read_text(encoding="utf-8") if path.exists() else ""
    return _cache[stem]


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().strip())


def _find_substring(quote: str, text: str) -> str | None:
    """Найти дословную подстроку или лучшее окно в документе."""
    q = quote.strip()
    if not q:
        return None
    if q in text:
        return q
    nq, nt = _normalize(q), _normalize(text)
    if nq in nt:
        # восстановить регистр из оригинала по позиции
        start = nt.index(nq)
        return text[start : start + len(q)]
    # sliding window по словам (≥3 слов совпадают подряд)
    words = [w for w in re.findall(r"\w+", q) if len(w) > 2]
    if len(words) >= 3:
        pat = r".{0,40}".join(re.escape(w) for w in words[:5])
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(0).strip()
    # короткий probe 25 символов
    probe = q[:25]
    if probe.lower() in text.lower():
        idx = text.lower().index(probe.lower())
        return text[idx : idx + min(len(q), 200)]
    return None


def snap_citations(citations: list[Citation]) -> list[Citation]:
    """Подтянуть цитаты к ближайшей дословной подстроке в документе."""
    fixed: list[Citation] = []
    for c in citations:
        doc = _doc_text(c.doc_id)
        snapped = _find_substring(c.quote, doc)
        if snapped:
            fixed.append(c.model_copy(update={"quote": snapped}))
        else:
            fixed.append(c)
    return fixed


def check_citations(citations: list[Citation], chunk_texts: list[str] | None = None) -> list[dict]:
    """Ghost = цитата не найдена ни в полном документе, ни в чанках."""
    ghosts: list[dict] = []
    pool = " ".join(chunk_texts or [])
    for c in citations:
        doc = _doc_text(c.doc_id)
        if _find_substring(c.quote, doc) or (pool and _find_substring(c.quote, pool)):
            continue
        ghosts.append({"doc_id": c.doc_id, "quote": c.quote, "speaker": c.speaker})
    return ghosts
