"""Text chunking and vector retrieval."""

from __future__ import annotations

import numpy as np

from config import settings


def chunk_text(text: str, chunk_size: int | None = None, overlap: int | None = None) -> list[str]:
    chunk_size = chunk_size or settings.chunk_size
    overlap = overlap or settings.chunk_overlap
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = end - overlap
    return [c for c in chunks if len(c) > 60]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float64)
    vb = np.array(b, dtype=np.float64)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


def retrieve_top_k(
    query_embedding: list[float],
    chunks: list[dict],
    k: int = 8,
) -> list[dict]:
    scored = []
    for ch in chunks:
        emb = ch.get("embedding") or []
        if not emb:
            continue
        sim = cosine_similarity(query_embedding, emb)
        scored.append({**ch, "similarity": round(sim, 4)})
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:k]
