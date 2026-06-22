"""Инструменты агента (обёртки над RAG и корпусом)."""

from __future__ import annotations

import json
from typing import Any

from rag import grep_corpus, list_speakers, load_doc_text, retrieve

# Счётчики для path-метрик (сбрасываются в pipeline)
_stats: dict[str, Any] = {
    "retrieval_calls": 0,
    "tools_used": [],
    "chunks_read": 0,
}


def reset_stats() -> None:
    _stats["retrieval_calls"] = 0
    _stats["tools_used"] = []
    _stats["chunks_read"] = 0


def get_stats() -> dict:
    return dict(_stats)


def _log_tool(name: str) -> None:
    _stats["tools_used"].append(name)


def grep_corpus_tool(pattern: str) -> dict:
    """Точный поиск термина по всем интервью (Enterprise Plus, Kubernetes, СБП…)."""
    _log_tool("grep_corpus")
    hits = grep_corpus(pattern)
    return {"pattern": pattern, "hits": hits, "count": len(hits)}


def search_kb(query: str, k: int = 5) -> dict:
    """Семантический поиск по корпусу интервью."""
    _log_tool("search_kb")
    _stats["retrieval_calls"] += 1
    hits = retrieve(query, k=k)
    ids = hits["ids"][0]
    docs = hits["documents"][0]
    metas = hits["metadatas"][0]
    _stats["chunks_read"] += len(ids)
    items = []
    for cid, doc, meta in zip(ids, docs, metas):
        items.append(
            {
                "chunk_id": cid,
                "source": meta.get("source"),
                "excerpt": doc[:600],
            }
        )
    return {"query": query, "hits": items, "count": len(items)}


def get_excerpt(doc_id: str, max_chars: int = 1200) -> dict:
    """Получить фрагмент полного текста интервью по doc_id."""
    _log_tool("get_excerpt")
    stem = doc_id.split("__")[0]
    text = load_doc_text(stem)
    return {"doc_id": stem, "excerpt": text[:max_chars], "total_chars": len(text)}


def list_speakers_tool() -> dict:
    """Список всех интервью и ролей респондентов."""
    _log_tool("list_speakers")
    return {"speakers": list_speakers()}


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "grep_corpus",
            "description": "Точный поиск термина в корпусе (тарифы, протоколы, технологии)",
            "parameters": {
                "type": "object",
                "properties": {"pattern": {"type": "string"}},
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_kb",
            "description": "Семантический поиск по архиву интервью CloudPay",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "k": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_excerpt",
            "description": "Прочитать начало интервью по doc_id (cloudpay_dev_ivan)",
            "parameters": {
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string"},
                    "max_chars": {"type": "integer", "default": 1200},
                },
                "required": ["doc_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_speakers",
            "description": "Список всех документов-интервью",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

TOOLS_IMPL = {
    "search_kb": search_kb,
    "grep_corpus": grep_corpus_tool,
    "get_excerpt": get_excerpt,
    "list_speakers": list_speakers_tool,
}


def exec_tool(name: str, args: dict) -> dict:
    fn = TOOLS_IMPL.get(name)
    if fn is None:
        return {"error": f"unknown tool {name}"}
    try:
        return fn(**args)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
