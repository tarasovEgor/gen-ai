"""
RAG-пайплайн: ChromaDB + dense retrieval + LLM (structured RAGAnswer).

Две стратегии чанкинга:
  A) fixed-size — каждые 2000 символов без перекрытия
  B) recursive — RecursiveCharacterTextSplitter(400, overlap=80)

Команды:
    python pipeline.py ingest --strategy fixed
    python pipeline.py ingest --strategy recursive
    python pipeline.py ask "Кто жаловался на webhook?" --strategy recursive
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from langchain_text_splitters import RecursiveCharacterTextSplitter
from llm_client import get_model, make_client
from schema import RAGAnswer

client = make_client()
MODEL = get_model()
DATA_DIR = Path(__file__).parent / "data"
CHROMA_PATH = Path(__file__).parent / "chroma_db"

print("Загружаю эмбеддер...", flush=True)
_t0 = time.time()
EMBED_FN = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="paraphrase-multilingual-MiniLM-L12-v2",
)
print(f"Эмбеддер готов за {time.time() - _t0:.1f}с", flush=True)

chroma = chromadb.PersistentClient(path=str(CHROMA_PATH))

RECURSIVE_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=400,
    chunk_overlap=80,
    separators=["\n\n", "\n", ". ", "? ", "! ", " "],
)


def chunk_fixed(text: str, chunk_size: int = 2000) -> list[str]:
    """Стратегия A: фиксированные чанки по 2000 символов без overlap."""
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


def chunk_recursive(text: str) -> list[str]:
    """Стратегия B: recursive splitter по абзацам/предложениям."""
    return [c.strip() for c in RECURSIVE_SPLITTER.split_text(text) if c.strip()]


def collection_name(strategy: str) -> str:
    if strategy not in ("fixed", "recursive"):
        raise ValueError(f"strategy must be fixed|recursive, got {strategy!r}")
    return f"cloudpay_{strategy}"


def get_collection(strategy: str):
    return chroma.get_or_create_collection(
        name=collection_name(strategy),
        embedding_function=EMBED_FN,
        metadata={"hnsw:space": "cosine"},
    )


def ingest(strategy: str) -> int:
    chunk_fn = chunk_fixed if strategy == "fixed" else chunk_recursive
    coll = get_collection(strategy)

    try:
        chroma.delete_collection(collection_name(strategy))
    except Exception:
        pass
    coll = get_collection(strategy)

    all_chunks: list[str] = []
    all_ids: list[str] = []
    all_meta: list[dict] = []

    for f in sorted(DATA_DIR.glob("*.txt")):
        if f.name == "gold.json":
            continue
        text = f.read_text(encoding="utf-8")
        chunks = chunk_fn(text)
        for i, c in enumerate(chunks):
            cid = f"{f.stem}__{i}"
            all_chunks.append(c)
            all_ids.append(cid)
            all_meta.append({"source": f.stem, "chunk_id": i, "strategy": strategy})
        print(f"  [{strategy}] {f.stem}: {len(chunks)} чанков")

    coll.add(documents=all_chunks, ids=all_ids, metadatas=all_meta)
    n = coll.count()
    print(f"\nИндексировано ({strategy}): {n} чанков")
    return n


def retrieve(strategy: str, query: str, k: int = 5) -> dict:
    coll = get_collection(strategy)
    if coll.count() == 0:
        raise RuntimeError(
            f"Коллекция {collection_name(strategy)} пуста. "
            f"Запусти: python pipeline.py ingest --strategy {strategy}"
        )
    return coll.query(query_texts=[query], n_results=k)


def build_prompt(query: str, hits: dict) -> str:
    docs = hits["documents"][0]
    ids = hits["ids"][0]
    ctx = "\n\n---\n\n".join(f"[{i}]\n{d}" for i, d in zip(ids, docs))
    return (
        "Ты отвечаешь на вопрос по архиву интервью о платформе CloudPay. "
        "Опирайся ТОЛЬКО на контекст. Если ответа нет — скажи прямо.\n\n"
        "Правила:\n"
        "1. Только факты из контекста.\n"
        "2. quotes — 1-5 точных цитат с именами.\n"
        "3. sources — id чанков (формат 'cloudpay_dev_ivan__0').\n"
        "4. confidence: 0.9+ при прямом ответе, 0.5-0.8 при сборке, <0.5 если нет данных.\n\n"
        f"Контекст:\n{ctx}\n\n"
        f"Вопрос: {query}\n\n"
        "Ответ:"
    )


def ask(query: str, strategy: str = "recursive", k: int = 5) -> RAGAnswer:
    print(f"Поиск ({strategy})...", flush=True)
    t0 = time.time()
    hits = retrieve(strategy, query, k=k)
    found = hits["ids"][0]
    print(f"   {len(found)} чанков за {time.time() - t0:.1f}с: {', '.join(found[:5])}", flush=True)

    print("Генерация...", flush=True)
    t1 = time.time()
    prompt = build_prompt(query, hits)
    resp: RAGAnswer = client.chat.completions.create(
        model=MODEL,
        response_model=RAGAnswer,
        max_retries=3,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    print(f"   ответ за {time.time() - t1:.1f}с", flush=True)

    print("\n" + "=" * 60)
    print(f"ВОПРОС: {query}")
    print("=" * 60)
    print(resp)
    print("\n--- источники ---")
    for i in found:
        print(f"  {i}")
    return resp


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    ing = sub.add_parser("ingest")
    ing.add_argument("--strategy", choices=["fixed", "recursive"], required=True)

    q = sub.add_parser("ask")
    q.add_argument("question")
    q.add_argument("--strategy", choices=["fixed", "recursive"], default="recursive")
    q.add_argument("--k", type=int, default=5)

    args = parser.parse_args()
    if args.cmd == "ingest":
        ingest(args.strategy)
    elif args.cmd == "ask":
        ask(args.question, strategy=args.strategy, k=args.k)


if __name__ == "__main__":
    main()
