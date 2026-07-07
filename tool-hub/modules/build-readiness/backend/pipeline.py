"""Indexing and analysis pipelines."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from capabilities import capability_match_score, extract_capabilities
from config import settings
from crawler import crawl_website
from domain_seed import ensure_market_domains, missing_verdict_domains
from page_index import (
    load_indexed_pages,
    load_indexed_video_ids,
    merge_capabilities,
    page_content_hash,
    backfill_page_hashes,
)
from database import (
    BuildReadinessProfile,
    BuildReadinessChunk,
    BuildReadinessCapability,
    BuildReadinessVerdict,
    BuildReadinessJob,
    BuildReadinessIndexRun,
    BuildReadinessAnalysisRun,
)
from llm_client import embed_texts
from market_bridge import fetch_latest_market_scores, get_market_meta
from rag import chunk_text, retrieve_top_k
from verdict import compute_verdict_label, generate_verdict, ensure_strengthen_suggestions


def _sanitize_for_db(value):
    """Remove null bytes — Postgres JSONB rejects \\u0000."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, dict):
        return {k: _sanitize_for_db(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_db(v) for v in value]
    return value


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


def run_index_website(job_id: str, db: Session, *, full: bool = False) -> None:
    job = db.query(BuildReadinessJob).filter(BuildReadinessJob.id == job_id).first()
    if not job:
        return
    try:
        profile = get_or_create_profile(db)
        incremental = not full
        if incremental:
            backfill_page_hashes(db, profile.id)
        existing_hashes = {} if full else load_indexed_pages(db, profile.id)

        job.status = "crawling"
        job.progress = {
            "step": "crawling",
            "url": profile.website_url,
            "mode": "full" if full else "incremental",
            "already_indexed": len(existing_hashes),
        }
        db.commit()

        def on_crawl_progress(pages_done: int, visited: int):
            job.progress = {
                "step": "crawling",
                "pages_done": pages_done,
                "visited": visited,
                "mode": "full" if full else "incremental",
            }
            db.commit()

        pages = crawl_website(
            profile.website_url,
            on_progress=on_crawl_progress,
            known_urls=set(existing_hashes.keys()),
        )

        to_embed: list[dict] = []
        unchanged = 0
        for page in pages:
            h = page_content_hash(page["text"])
            page["_hash"] = h
            if incremental and existing_hashes.get(page["url"]) == h:
                unchanged += 1
                continue
            to_embed.append(page)

        job.status = "embedding"
        job.progress = {
            "step": "embedding",
            "crawled": len(pages),
            "new_or_changed": len(to_embed),
            "unchanged_skipped": unchanged,
        }
        db.commit()

        if full:
            db.query(BuildReadinessChunk).filter(
                BuildReadinessChunk.profile_id == profile.id,
                BuildReadinessChunk.source_type == "website",
            ).delete()
            db.query(BuildReadinessCapability).filter(
                BuildReadinessCapability.profile_id == profile.id
            ).delete()
            db.commit()
            to_embed = pages
        elif to_embed:
            changed_urls = [p["url"] for p in to_embed]
            db.query(BuildReadinessChunk).filter(
                BuildReadinessChunk.profile_id == profile.id,
                BuildReadinessChunk.source_type == "website",
                BuildReadinessChunk.source_url.in_(changed_urls),
            ).delete(synchronize_session=False)
            db.commit()
        elif incremental:
            job.status = "done"
            job.progress = {
                "pages": len(existing_hashes),
                "chunks": db.query(BuildReadinessChunk).filter(
                    BuildReadinessChunk.profile_id == profile.id
                ).count(),
                "unchanged_skipped": unchanged,
                "message": "No page changes detected — skipped re-embedding",
            }
            job.completed_at = datetime.utcnow()
            db.commit()
            return

        total_chunks = 0
        batch_size = 40
        for i in range(0, len(to_embed), batch_size):
            batch = to_embed[i : i + batch_size]
            chunk_records = []
            for page in batch:
                for j, piece in enumerate(chunk_text(page["text"])):
                    chunk_records.append({
                        "url": page["url"],
                        "title": page["title"],
                        "content": piece,
                        "chunk_index": j,
                        "content_hash": page["_hash"],
                    })
            embeddings = embed_texts([b["content"] for b in chunk_records])
            for rec, emb in zip(chunk_records, embeddings):
                db.add(BuildReadinessChunk(
                    profile_id=profile.id,
                    source_type="website",
                    source_url=rec["url"],
                    title=rec["title"],
                    content=rec["content"],
                    embedding=emb,
                    metadata_json={
                        "chunk_index": rec["chunk_index"],
                        "content_hash": rec["content_hash"],
                    },
                ))
                total_chunks += 1
            db.commit()

        if full:
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
        elif to_embed:
            existing_caps = [
                {
                    "category": c.category,
                    "name": c.name,
                    "evidence_count": c.evidence_count,
                    "sample_urls": list(c.sample_urls or []),
                    "depth_score": float(c.depth_score or 0),
                }
                for c in db.query(BuildReadinessCapability).filter(
                    BuildReadinessCapability.profile_id == profile.id
                ).all()
            ]
            new_caps = extract_capabilities(to_embed)
            merged = merge_capabilities(existing_caps, new_caps)
            db.query(BuildReadinessCapability).filter(
                BuildReadinessCapability.profile_id == profile.id
            ).delete()
            for cap in merged:
                db.add(BuildReadinessCapability(
                    profile_id=profile.id,
                    category=cap["category"],
                    name=cap["name"],
                    evidence_count=cap["evidence_count"],
                    sample_urls=cap["sample_urls"],
                    depth_score=cap["depth_score"],
                ))
        db.commit()

        total_chunk_count = db.query(BuildReadinessChunk).filter(
            BuildReadinessChunk.profile_id == profile.id
        ).count()
        cap_count = db.query(BuildReadinessCapability).filter(
            BuildReadinessCapability.profile_id == profile.id
        ).count()
        unique_pages = db.query(BuildReadinessChunk.source_url).filter(
            BuildReadinessChunk.profile_id == profile.id,
            BuildReadinessChunk.source_type == "website",
        ).distinct().count()

        profile.last_indexed_at = datetime.utcnow()
        profile.pages_indexed = unique_pages
        profile.chunks_indexed = total_chunk_count
        profile.updated_at = datetime.utcnow()

        db.add(BuildReadinessIndexRun(
            profile_id=profile.id,
            job_id=job.id,
            source_type="website",
            pages_indexed=len(to_embed) if incremental else len(pages),
            chunks_indexed=total_chunks,
            capabilities_found=cap_count,
            indexed_at=profile.last_indexed_at,
        ))
        db.commit()

        job.status = "done"
        job.progress = {
            "pages": unique_pages,
            "chunks": total_chunk_count,
            "capabilities": cap_count,
            "new_or_changed": len(to_embed),
            "unchanged_skipped": unchanged,
            "mode": "full" if full else "incremental",
        }
        job.completed_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        db.rollback()
        job = db.query(BuildReadinessJob).filter(BuildReadinessJob.id == job_id).first()
        if job:
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
            FROM (
                SELECT id, source_url, title, transcript, summary_json, completed_at
                FROM video_scraper_jobs
                WHERE status IN ('done', 'partial')
                  AND COALESCE(is_batch, false) = false
                  AND transcript IS NOT NULL
                  AND length(transcript) > 100
                UNION ALL
                SELECT i.id, i.video_url, i.title, i.transcript, i.summary_json, i.completed_at
                FROM video_scraper_items i
                WHERE i.status = 'done'
                  AND i.transcript IS NOT NULL
                  AND length(i.transcript) > 100
            ) videos
            ORDER BY completed_at DESC NULLS LAST
            LIMIT 50
        """)).mappings().all()

        indexed_ids = load_indexed_video_ids(db, profile.id)
        new_rows = [r for r in rows if r["id"] not in indexed_ids]

        job.progress = {
            "step": "embedding",
            "videos_total": len(rows),
            "videos_new": len(new_rows),
            "videos_skipped": len(rows) - len(new_rows),
        }
        db.commit()

        if not new_rows:
            job.status = "done"
            job.progress = {
                "videos": profile.videos_indexed,
                "message": "No new video transcripts to index",
            }
            job.completed_at = datetime.utcnow()
            db.commit()
            return

        video_count = profile.videos_indexed or 0
        chunk_total = 0
        for row in new_rows:
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

        db.add(BuildReadinessIndexRun(
            profile_id=profile.id,
            job_id=job.id,
            source_type="videos",
            pages_indexed=0,
            chunks_indexed=chunk_total,
            capabilities_found=0,
            indexed_at=datetime.utcnow(),
        ))
        db.commit()

        job.status = "done"
        job.progress = {"videos": video_count, "chunks_added": chunk_total}
        job.completed_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        db.rollback()
        job = db.query(BuildReadinessJob).filter(BuildReadinessJob.id == job_id).first()
        if job:
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

        market_meta = get_market_meta(db)
        market_fetched_at = None
        if market_meta.get("latest_fetch"):
            market_fetched_at = datetime.fromisoformat(
                market_meta["latest_fetch"].replace("Z", "+00:00")
            ).replace(tzinfo=None)

        chunks = _load_chunks(db, profile.id)
        capabilities = _load_capabilities(db, profile.id)

        from pipeline_status import find_incomplete_batch_id

        domain_count = len(market)
        resume_batch = find_incomplete_batch_id(db, profile.id, domain_count)
        if resume_batch:
            batch_id = resume_batch
            existing_rows = (
                db.query(BuildReadinessVerdict)
                .filter(
                    BuildReadinessVerdict.profile_id == profile.id,
                    BuildReadinessVerdict.analysis_batch_id == batch_id,
                )
                .all()
            )
            completed_domains = {v.domain_name for v in existing_rows}
            go_count = sum(1 for v in existing_rows if v.verdict == "GO")
        else:
            batch_id = uuid.uuid4()
            completed_domains = set()
            go_count = 0

        job.status = "analyzing"
        job.progress = {
            "domains": domain_count,
            "domains_done": len(completed_domains),
            "batch_id": str(batch_id),
            "resumed": bool(resume_batch),
        }
        db.commit()

        for i, (domain_name, domain_data) in enumerate(market.items()):
            if domain_name in completed_domains:
                continue

            job.progress = {
                "domains": domain_count,
                "domains_done": len(completed_domains),
                "current_domain": domain_name,
                "batch_id": str(batch_id),
                "resumed": bool(resume_batch),
            }
            db.commit()

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

            try:
                verdict_json, validated, notes = generate_verdict(
                    domain_data, cap_score, matched, retrieved
                )
            except Exception as exc:
                verdict_json = {
                    "verdict": label,
                    "can_build": cap_score >= 50,
                    "confidence": "low",
                    "headline": f"Algorithmic fit score — LLM step failed ({str(exc)[:120]})",
                    "market_need": domain_data.get("product_landscape", {}).get(
                        "demand_summary", "See Market Depth for demand signals"
                    ),
                    "our_strengths": matched[:5],
                    "gaps": ["Full narrative unavailable — re-run Fit Analysis if this persists"],
                    "how_to_build": {
                        "phase_1": "Validate demand with Market Depth",
                        "phase_2": "Map capabilities to product types",
                        "phase_3": "Pilot with existing service line",
                    },
                    "revenue_path": "Align with top revenue model from market landscape",
                    "depth_assessment": f"Capability score: {cap_score}/100",
                }
                validated = False
                notes = str(exc)

            verdict_json = ensure_strengthen_suggestions(verdict_json, domain_name)
            if verdict_json.get("verdict"):
                label = verdict_json["verdict"]
            if label == "GO":
                go_count += 1

            domain_market_at = None
            if domain_data.get("fetched_at"):
                domain_market_at = datetime.fromisoformat(
                    domain_data["fetched_at"].replace("Z", "+00:00")
                ).replace(tzinfo=None)

            citations = _sanitize_for_db([
                {
                    "url": c.get("source_url"),
                    "title": c.get("title"),
                    "source_type": c.get("source_type"),
                    "similarity": c.get("similarity"),
                    "excerpt": c.get("content", "")[:300],
                }
                for c in retrieved[:5]
            ])

            verdict_payload = _sanitize_for_db({
                **verdict_json,
                "validation_passed": validated,
                "validation_notes": notes,
                "matched_capabilities": matched,
                "algorithmic_label": compute_verdict_label(market_score, cap_score),
                "market_fetched_at": domain_data.get("fetched_at"),
                "company_indexed_at": profile.last_indexed_at.isoformat() if profile.last_indexed_at else None,
            })

            db.add(BuildReadinessVerdict(
                profile_id=profile.id,
                analysis_batch_id=batch_id,
                domain_id=domain_data.get("domain_id"),
                domain_name=domain_name,
                track=domain_data.get("track", ""),
                market_score=market_score,
                capability_score=cap_score,
                opportunity_score=opportunity,
                verdict=label,
                verdict_json=verdict_payload,
                citations=citations,
                market_fetched_at=domain_market_at or market_fetched_at,
                company_indexed_at=profile.last_indexed_at,
            ))
            db.commit()
            completed_domains.add(domain_name)
            job.progress = {
                "domains": domain_count,
                "domains_done": len(completed_domains),
                "current_domain": domain_name,
                "batch_id": str(batch_id),
                "resumed": bool(resume_batch),
            }
            db.commit()

        analysis_run = db.query(BuildReadinessAnalysisRun).filter(
            BuildReadinessAnalysisRun.id == batch_id
        ).first()
        if analysis_run:
            analysis_run.market_fetched_at = market_fetched_at
            analysis_run.company_indexed_at = profile.last_indexed_at
            analysis_run.domains_analyzed = domain_count
            analysis_run.go_count = go_count
            analysis_run.analyzed_at = datetime.utcnow()
        else:
            db.add(BuildReadinessAnalysisRun(
                id=batch_id,
                profile_id=profile.id,
                job_id=job.id,
                market_fetched_at=market_fetched_at,
                company_indexed_at=profile.last_indexed_at,
                domains_analyzed=domain_count,
                go_count=go_count,
                analyzed_at=datetime.utcnow(),
            ))
        db.commit()

        job.status = "done"
        job.progress = {
            "domains": domain_count,
            "domains_done": domain_count,
            "verdicts": domain_count,
            "batch_id": str(batch_id),
            "go_count": go_count,
            "resumed": bool(resume_batch),
        }
        job.completed_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        db.rollback()
        job = db.query(BuildReadinessJob).filter(BuildReadinessJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.error = str(e)
            job.completed_at = datetime.utcnow()
            db.commit()
