"""RAG: ChromaDB + hybrid keyword boost."""

from __future__ import annotations

import re
import time
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from langchain_text_splitters import RecursiveCharacterTextSplitter

CORPUS_DIR = Path(__file__).parent / "input" / "corpus"
CHROMA_PATH = Path(__file__).parent / "chroma_db"
COLLECTION = "cloudpay_recursive"

_EMBED_FN: embedding_functions.EmbeddingFunction | None = None
_chroma: chromadb.PersistentClient | None = None

RECURSIVE_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=400,
    chunk_overlap=80,
    separators=["\n\n", "\n", ". ", "? ", "! ", " "],
)

# Точные фразы для keyword-boost (improves recall on rare terms)
PHRASE_PATTERNS = [
    r"Enterprise\s+Plus",
    r"Enterprise\b",
    r"PCI\s+DSS(?:\s+Level\s+1)?",
    r"OAuth\s*2\.1",
    r"Kubernetes",
    r"HMAC",
    r"СБП",
    r"webhook",
    r"sandbox",
    r"Stripe",
    r"Kubernetes",
    r"UI\b",
    r"личного кабинета",
]


def _embed_fn():
    global _EMBED_FN
    if _EMBED_FN is None:
        _EMBED_FN = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="paraphrase-multilingual-MiniLM-L12-v2",
        )
    return _EMBED_FN


def _client() -> chromadb.PersistentClient:
    global _chroma
    if _chroma is None:
        CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        _chroma = chromadb.PersistentClient(path=str(CHROMA_PATH))
    return _chroma


def get_collection():
    return _client().get_or_create_collection(
        name=COLLECTION,
        embedding_function=_embed_fn(),
        metadata={"hnsw:space": "cosine"},
    )


def ingest(*, verbose: bool = True) -> int:
    coll = get_collection()
    try:
        _client().delete_collection(COLLECTION)
    except Exception:
        pass
    coll = get_collection()

    all_chunks: list[str] = []
    all_ids: list[str] = []
    all_meta: list[dict] = []

    for f in sorted(CORPUS_DIR.glob("*.txt")):
        text = f.read_text(encoding="utf-8")
        chunks = [c.strip() for c in RECURSIVE_SPLITTER.split_text(text) if c.strip()]
        for i, c in enumerate(chunks):
            all_chunks.append(c)
            all_ids.append(f"{f.stem}__{i}")
            all_meta.append({"source": f.stem, "chunk_id": i})
        if verbose:
            print(f"  {f.stem}: {len(chunks)} чанков")

    coll.add(documents=all_chunks, ids=all_ids, metadatas=all_meta)
    n = coll.count()
    if verbose:
        print(f"Индексировано: {n} чанков → {COLLECTION}")
    return n


def retrieve(query: str, k: int = 5) -> dict:
    coll = get_collection()
    if coll.count() == 0:
        raise RuntimeError("Индекс пуст. Запусти: python pipeline.py --ingest")
    return coll.query(query_texts=[query], n_results=k)


def extract_phrases(question: str) -> list[str]:
    found: list[str] = []
    for pat in PHRASE_PATTERNS:
        for m in re.finditer(pat, question, re.IGNORECASE):
            found.append(m.group(0))
    return list(dict.fromkeys(found))


def grep_corpus(pattern: str, *, context: int = 120) -> list[dict]:
    """Точный поиск подстроки по всем документам."""
    needle = pattern.lower()
    out: list[dict] = []
    for f in sorted(CORPUS_DIR.glob("*.txt")):
        text = f.read_text(encoding="utf-8")
        hay = text.lower()
        if needle not in hay:
            continue
        idx = hay.find(needle)
        snippet = text[max(0, idx - context) : idx + len(pattern) + context]
        out.append({"doc_id": f.stem, "pattern": pattern, "snippet": snippet.strip()})
    return out


def hybrid_retrieve(question: str, k: int = 5) -> dict:
    """Semantic + keyword boost: объединяем top-k и grep-хиты."""
    sem = retrieve(question, k=k)
    ids = list(sem["ids"][0])
    docs = list(sem["documents"][0])
    metas = list(sem["metadatas"][0])

    seen = set(ids)
    for phrase in extract_phrases(question):
        for hit in grep_corpus(phrase):
            kid = f"{hit['doc_id']}__kw_{phrase[:12]}"
            if kid in seen:
                continue
            seen.add(kid)
            ids.append(kid)
            docs.append(hit["snippet"])
            metas.append({"source": hit["doc_id"], "chunk_id": -1, "keyword": phrase})

    return {"ids": [ids], "documents": [docs], "metadatas": [metas]}


def load_doc_text(doc_id: str) -> str:
    path = CORPUS_DIR / f"{doc_id.split('__')[0]}.txt"
    if not path.exists():
        raise FileNotFoundError(doc_id)
    return path.read_text(encoding="utf-8")


def list_speakers() -> list[dict]:
    rows = []
    for f in sorted(CORPUS_DIR.glob("*.txt")):
        first = f.read_text(encoding="utf-8").split("\n", 1)[0]
        rows.append({"doc_id": f.stem, "header": first.strip("# ").strip()})
    return rows


def ensure_index() -> None:
    if get_collection().count() == 0:
        print("Индекс не найден — ingest...", flush=True)
        t0 = time.perf_counter()
        ingest()
        print(f"Готово за {time.perf_counter() - t0:.1f}с", flush=True)
