"""Indexing and analysis pipelines."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from capabilities import capability_match_score, extract_capabilities
from config import settings
from crawler import crawl_website
from database import (
    BuildReadinessProfile,
    BuildReadinessChunk,
    BuildReadinessCapability,
    BuildReadinessVerdict,
    BuildReadinessJob,
)
from llm_client import embed_texts
from market_bridge import fetch_latest_market_scores
from rag import chunk_text, retrieve_top_k
from verdict import compute_verdict_label, generate_verdict


def get_or_create_profile(db: Session) -> BuildReadinessProfile:
    profile = (
        db.query(BuildReadinessProfile)
        .filter(BuildReadinessProfile.is_active == True)
        .order_by(BuildReadinessProfile.created_at.desc())
        .first()
    )
    if profile:
        return profile
    profile = BuildReadinessProfile(
        company_name=settings.default_company_name,
        website_url=settings.default_company_url,
        is_active=True,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def run_index_website(job_id: str, db: Session) -> None:
    job = db.query(BuildReadinessJob).filter(BuildReadinessJob.id == job_id).first()
    if not job:
        return
    try:
        profile = get_or_create_profile(db)
        job.status = "crawling"
        job.progress = {"step": "crawling", "url": profile.website_url}
        db.commit()

        def on_crawl_progress(pages_done: int, visited: int):
            job.progress = {"step": "crawling", "pages_done": pages_done, "visited": visited}
            db.commit()

        pages = crawl_website(profile.website_url, on_progress=on_crawl_progress)
        job.status = "embedding"
        job.progress = {"step": "embedding", "pages": len(pages)}
        db.commit()

        db.query(BuildReadinessChunk).filter(
            BuildReadinessChunk.profile_id == profile.id,
            BuildReadinessChunk.source_type == "website",
        ).delete()
        db.query(BuildReadinessCapability).filter(
            BuildReadinessCapability.profile_id == profile.id
        ).delete()
        db.commit()

        chunk_records: list[dict] = []
        for page in pages:
            for i, piece in enumerate(chunk_text(page["text"])):
                chunk_records.append({
                    "url": page["url"],
                    "title": page["title"],
                    "content": piece,
                    "chunk_index": i,
                })

        batch_size = 40
        total_chunks = 0
        for i in range(0, len(chunk_records), batch_size):
            batch = chunk_records[i : i + batch_size]
            embeddings = embed_texts([b["content"] for b in batch])
            for rec, emb in zip(batch, embeddings):
                db.add(BuildReadinessChunk(
                    profile_id=profile.id,
                    source_type="website",
                    source_url=rec["url"],
                    title=rec["title"],
                    content=rec["content"],
                    embedding=emb,
                    metadata_json={"chunk_index": rec["chunk_index"]},
                ))
                total_chunks += 1
            db.commit()

        caps = extract_capabilities(pages)
        for cap in caps:
            db.add(BuildReadinessCapability(
                profile_id=profile.id,
                category=cap["category"],
                name=cap["name"],
                evidence_count=cap["evidence_count"],
                sample_urls=cap["sample_urls"],
                depth_score=cap["depth_score"],
            ))
        db.commit()

        profile.last_indexed_at = datetime.utcnow()
        profile.pages_indexed = len(pages)
        profile.chunks_indexed = total_chunks
        profile.updated_at = datetime.utcnow()
        db.commit()

        job.status = "done"
        job.progress = {"pages": len(pages), "chunks": total_chunks, "capabilities": len(caps)}
        job.completed_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        job.status = "failed"
        job.error = str(e)
        job.completed_at = datetime.utcnow()
        db.commit()


def run_index_videos(job_id: str, db: Session) -> None:
    job = db.query(BuildReadinessJob).filter(BuildReadinessJob.id == job_id).first()
    if not job:
        return
    try:
        profile = get_or_create_profile(db)
        job.status = "fetching"
        db.commit()

        rows = db.execute(text("""
            SELECT id::text, source_url, title, transcript, summary_json
            FROM video_scraper_jobs
            WHERE status = 'done' AND transcript IS NOT NULL AND length(transcript) > 100
            ORDER BY completed_at DESC NULLS LAST
            LIMIT 50
        """)).mappings().all()

        db.query(BuildReadinessChunk).filter(
            BuildReadinessChunk.profile_id == profile.id,
            BuildReadinessChunk.source_type == "video",
        ).delete()
        db.commit()

        video_count = 0
        chunk_total = 0
        for row in rows:
            transcript = row["transcript"] or ""
            title = row["title"] or row["source_url"]
            pieces = chunk_text(transcript)
            if not pieces:
                continue
            embeddings = embed_texts(pieces)
            for i, (piece, emb) in enumerate(zip(pieces, embeddings)):
                db.add(BuildReadinessChunk(
                    profile_id=profile.id,
                    source_type="video",
                    source_url=row["source_url"],
                    title=title,
                    content=piece,
                    embedding=emb,
                    metadata_json={"video_job_id": row["id"], "chunk_index": i},
                ))
                chunk_total += 1
            video_count += 1
        db.commit()

        profile.videos_indexed = video_count
        profile.chunks_indexed = (
            db.query(BuildReadinessChunk)
            .filter(BuildReadinessChunk.profile_id == profile.id)
            .count()
        )
        profile.updated_at = datetime.utcnow()
        db.commit()

        job.status = "done"
        job.progress = {"videos": video_count, "chunks_added": chunk_total}
        job.completed_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        job.status = "failed"
        job.error = str(e)
        job.completed_at = datetime.utcnow()
        db.commit()


def _load_chunks(db: Session, profile_id) -> list[dict]:
    rows = db.query(BuildReadinessChunk).filter(
        BuildReadinessChunk.profile_id == profile_id
    ).all()
    return [
        {
            "id": str(r.id),
            "source_type": r.source_type,
            "source_url": r.source_url,
            "title": r.title,
            "content": r.content,
            "embedding": r.embedding,
        }
        for r in rows
    ]


def _load_capabilities(db: Session, profile_id) -> list[dict]:
    rows = db.query(BuildReadinessCapability).filter(
        BuildReadinessCapability.profile_id == profile_id
    ).all()
    return [
        {
            "category": r.category,
            "name": r.name,
            "evidence_count": r.evidence_count,
            "depth_score": float(r.depth_score or 0),
            "sample_urls": list(r.sample_urls or []),
        }
        for r in rows
    ]


def run_analyze(job_id: str, db: Session) -> None:
    job = db.query(BuildReadinessJob).filter(BuildReadinessJob.id == job_id).first()
    if not job:
        return
    try:
        profile = get_or_create_profile(db)
        chunk_count = db.query(BuildReadinessChunk).filter(
            BuildReadinessChunk.profile_id == profile.id
        ).count()
        if chunk_count == 0:
            raise ValueError("No indexed content — run Index Website first")

        market = fetch_latest_market_scores(db)
        if not market:
            raise ValueError("No market depth data — refresh Market Depth Analyzer first")

        chunks = _load_chunks(db, profile.id)
        capabilities = _load_capabilities(db, profile.id)

        db.query(BuildReadinessVerdict).filter(
            BuildReadinessVerdict.profile_id == profile.id
        ).delete()
        db.commit()

        job.status = "analyzing"
        job.progress = {"domains": len(market)}
        db.commit()

        for domain_name, domain_data in market.items():
            product_types = [
                pt.get("product_type", "")
                for pt in domain_data.get("product_landscape", {}).get("product_types_in_demand", [])
            ]
            query = f"{domain_name} {' '.join(domain_data.get('keywords', []))} {' '.join(product_types)}"
            query_emb = embed_texts([query])[0]
            retrieved = retrieve_top_k(query_emb, chunks, k=8)

            cap_score, matched = capability_match_score(
                domain_data.get("keywords", []),
                product_types,
                capabilities,
                retrieved,
            )
            market_score = domain_data.get("market_score", 0)
            opportunity = round(market_score * 0.55 + cap_score * 0.45, 2)
            label = compute_verdict_label(market_score, cap_score)

            verdict_json, validated, notes = generate_verdict(
                domain_data, cap_score, matched, retrieved
            )
            if verdict_json.get("verdict"):
                label = verdict_json["verdict"]

            citations = [
                {
                    "url": c.get("source_url"),
                    "title": c.get("title"),
                    "source_type": c.get("source_type"),
                    "similarity": c.get("similarity"),
                    "excerpt": c.get("content", "")[:300],
                }
                for c in retrieved[:5]
            ]

            db.add(BuildReadinessVerdict(
                profile_id=profile.id,
                domain_id=domain_data.get("domain_id"),
                domain_name=domain_name,
                track=domain_data.get("track", ""),
                market_score=market_score,
                capability_score=cap_score,
                opportunity_score=opportunity,
                verdict=label,
                verdict_json={
                    **verdict_json,
                    "validation_passed": validated,
                    "validation_notes": notes,
                    "matched_capabilities": matched,
                    "algorithmic_label": compute_verdict_label(market_score, cap_score),
                },
                citations=citations,
            ))
        db.commit()

        job.status = "done"
        job.progress = {"verdicts": len(market)}
        job.completed_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        job.status = "failed"
        job.error = str(e)
        job.completed_at = datetime.utcnow()
        db.commit()
