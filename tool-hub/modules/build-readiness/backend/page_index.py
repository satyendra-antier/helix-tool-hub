"""Incremental indexing helpers — skip unchanged pages/embeddings."""

from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from database import BuildReadinessChunk


def page_content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def load_indexed_pages(db: Session, profile_id) -> dict[str, str]:
    """Map canonical page URL → content hash from stored chunks."""
    rows = db.query(BuildReadinessChunk).filter(
        BuildReadinessChunk.profile_id == profile_id,
        BuildReadinessChunk.source_type == "website",
    ).all()
    result: dict[str, str] = {}
    for row in rows:
        meta = row.metadata_json or {}
        h = meta.get("content_hash")
        if h:
            result[row.source_url] = h
    return result


def backfill_page_hashes(db: Session, profile_id) -> int:
    """Set content_hash on legacy chunks so incremental indexing can skip unchanged pages."""
    rows = db.query(BuildReadinessChunk).filter(
        BuildReadinessChunk.profile_id == profile_id,
        BuildReadinessChunk.source_type == "website",
    ).all()
    by_url: dict[str, list] = {}
    for row in rows:
        by_url.setdefault(row.source_url, []).append(row)

    updated = 0
    for _url, chunks in by_url.items():
        if any((c.metadata_json or {}).get("content_hash") for c in chunks):
            continue
        ordered = sorted(
            chunks,
            key=lambda c: (c.metadata_json or {}).get("chunk_index", 0),
        )
        combined = " ".join(c.content for c in ordered)
        h = page_content_hash(combined)
        for c in chunks:
            meta = dict(c.metadata_json or {})
            meta["content_hash"] = h
            c.metadata_json = meta
        updated += 1
    if updated:
        db.commit()
    return updated


def load_indexed_video_ids(db: Session, profile_id) -> set[str]:
    rows = db.query(BuildReadinessChunk).filter(
        BuildReadinessChunk.profile_id == profile_id,
        BuildReadinessChunk.source_type == "video",
    ).all()
    ids: set[str] = set()
    for row in rows:
        vid = (row.metadata_json or {}).get("video_job_id")
        if vid:
            ids.add(str(vid))
    return ids


def merge_capabilities(existing: list[dict], new_caps: list[dict]) -> list[dict]:
    """Merge capability extractions by (category, name)."""
    merged: dict[tuple[str, str], dict] = {}
    for cap in existing + new_caps:
        key = (cap["category"], cap["name"])
        if key not in merged:
            merged[key] = dict(cap)
            continue
        prev = merged[key]
        prev["evidence_count"] = max(
            int(prev.get("evidence_count") or 0),
            int(cap.get("evidence_count") or 0),
        )
        urls = list(dict.fromkeys(
            list(prev.get("sample_urls") or []) + list(cap.get("sample_urls") or [])
        ))
        prev["sample_urls"] = urls[:5]
        prev["depth_score"] = max(
            float(prev.get("depth_score") or 0),
            float(cap.get("depth_score") or 0),
        )
    results = list(merged.values())
    results.sort(key=lambda x: (-float(x.get("depth_score") or 0), -int(x.get("evidence_count") or 0)))
    return results[:80]
