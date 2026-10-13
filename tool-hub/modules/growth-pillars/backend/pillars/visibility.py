"""Pillar 4 - LLM Visibility: are AI assistants recommending us for the queries buyers ask?"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import settings
from database import VisibilityCheck, VisibilityQuery, get_db
from hub_clients import go_domains
from jobs import create_job, run_job_in_thread
from llm_client import chat, chat_json, llm_available
from text_match import normalize_domain, same_company

router = APIRouter(tags=["visibility"])

EXTRACT_PROMPT = """List every company, agency or vendor that the answer below recommends or names
as a provider, in the order they appear. Do not add any company that is not in the text.
Output JSON: {"companies": [str]}

Answer:
"""

RECOMMEND_PROMPT = """We are {company} ({url}). AI assistants were asked the buyer queries below.
For each we know whether we were mentioned and which competitors were named.

{data}

Suggest 5 concrete content or PR actions that would make assistants more likely to recommend us
for the queries where we are missing. Think: comparison pages, case studies with numbers,
third-party listings/directories, analyst or media mentions, technical guides, structured FAQs.
Output JSON: {{"recommendations": [{{"title": str, "why": str, "target_queries": [str], "format": str}}]}}"""


class QueryIn(BaseModel):
    query: str = Field(min_length=3)
    domain: Optional[str] = None


class SuggestRequest(BaseModel):
    per_domain: int = Field(default=2, ge=1, le=5)


def query_to_dict(q: VisibilityQuery) -> dict:
    return {
        "id": str(q.id),
        "query": q.query,
        "domain": q.domain,
        "active": q.active,
        "created_at": q.created_at.isoformat() if q.created_at else None,
    }


def check_to_dict(c: VisibilityCheck) -> dict:
    return {
        "id": str(c.id),
        "query_id": str(c.query_id),
        "query": c.query,
        "provider": c.provider,
        "model": c.model,
        "mentioned": c.mentioned,
        "rank": c.rank,
        "competitors": c.competitors or [],
        "citations": c.citations or [],
        "answer_excerpt": c.answer_excerpt,
        "checked_at": c.checked_at.isoformat() if c.checked_at else None,
    }


def _our_identity() -> tuple[str, str]:
    return settings.default_company_name, normalize_domain(settings.default_company_url)


def detect_mention(answer: str) -> bool:
    name, host = _our_identity()
    text = answer.lower()
    if host and host in text:
        return True
    return re.search(rf"\b{re.escape(name.lower())}\b", text) is not None


def extract_companies_fallback(answer: str) -> list[str]:
    names: list[str] = []
    for line in answer.splitlines():
        m = re.match(r"^\s*(?:\d+[.)]|[-*•])\s+\**([^*:\-–—(\n]{2,60})", line)
        if m:
            name = m.group(1).strip(" .*")
            if name and name.lower() not in {n.lower() for n in names}:
                names.append(name)
    return names


def extract_companies(answer: str) -> list[str]:
    if llm_available():
        try:
            data = chat_json(EXTRACT_PROMPT + answer[:6000])
            companies = [str(c).strip() for c in data.get("companies") or [] if str(c).strip()]
            if companies:
                return companies[:20]
        except Exception:  # noqa: BLE001
            pass
    return extract_companies_fallback(answer)[:20]


def ask_openai(query: str) -> tuple[str, list[str]]:
    return chat(query), []


def ask_perplexity(query: str) -> tuple[str, list[str]]:
    with httpx.Client(timeout=60) as client:
        resp = client.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {settings.perplexity_api_key}"},
            json={"model": settings.perplexity_model, "messages": [{"role": "user", "content": query}]},
        )
        resp.raise_for_status()
        data = resp.json()
    answer = data["choices"][0]["message"]["content"]
    return answer, [str(c) for c in data.get("citations") or []][:15]


def providers() -> list[tuple[str, str, callable]]:
    out = []
    if llm_available():
        out.append(("openai", settings.resolve_chat_model(), ask_openai))
    if settings.perplexity_api_key:
        out.append(("perplexity", settings.perplexity_model, ask_perplexity))
    return out


def check_query(db: Session, q: VisibilityQuery) -> list[VisibilityCheck]:
    name, _ = _our_identity()
    results = []
    for provider, model, ask in providers():
        try:
            answer, citations = ask(q.query)
        except Exception as exc:  # noqa: BLE001
            answer, citations = f"[error: {exc}]", []
        companies = extract_companies(answer) if not answer.startswith("[error") else []
        rank = next((i + 1 for i, c in enumerate(companies) if same_company(c, name)), None)
        mentioned = rank is not None or detect_mention(answer)
        competitors = [c for c in companies if not same_company(c, name)][:10]
        check = VisibilityCheck(
            query_id=q.id,
            query=q.query,
            provider=provider,
            model=model,
            mentioned=mentioned,
            rank=rank,
            competitors=competitors,
            citations=citations,
            answer_excerpt=answer[:1500],
        )
        db.add(check)
        results.append(check)
    db.commit()
    return results


def run_checks(db: Session) -> dict:
    if not providers():
        return {"checked": 0, "note": "Add OPENAI_API_KEY (and optionally PERPLEXITY_API_KEY) to run checks"}
    queries = db.query(VisibilityQuery).filter(VisibilityQuery.active.is_(True)).all()
    checks = 0
    mentioned = 0
    for q in queries:
        for c in check_query(db, q):
            checks += 1
            mentioned += int(bool(c.mentioned))
    return {"queries": len(queries), "checks": checks, "mentioned": mentioned}


def _latest_checks(db: Session) -> list[VisibilityCheck]:
    active_ids = {q.id for q in db.query(VisibilityQuery).filter(VisibilityQuery.active.is_(True)).all()}
    latest: dict[tuple, VisibilityCheck] = {}
    for c in db.query(VisibilityCheck).order_by(VisibilityCheck.checked_at.desc()).limit(2000).all():
        if c.query_id not in active_ids:
            continue
        key = (c.query_id, c.provider)
        if key not in latest:
            latest[key] = c
    return list(latest.values())


def latest_share(db: Session) -> float | None:
    checks = _latest_checks(db)
    if not checks:
        return None
    return round(sum(1 for c in checks if c.mentioned) / len(checks), 3)


def count_queries(db: Session) -> int:
    return db.query(VisibilityQuery).filter(VisibilityQuery.active.is_(True)).count()


def _template_queries(domain: str) -> list[str]:
    return [
        f"Best {domain} companies to hire",
        f"Who are the top {domain} development firms for enterprises?",
    ]


@router.get("/visibility/queries")
def list_queries(db: Session = Depends(get_db)):
    queries = db.query(VisibilityQuery).filter(VisibilityQuery.active.is_(True)).order_by(VisibilityQuery.created_at).all()
    return {"queries": [query_to_dict(q) for q in queries]}


@router.post("/visibility/queries")
def add_query(body: QueryIn, db: Session = Depends(get_db)):
    q = VisibilityQuery(query=body.query.strip(), domain=body.domain)
    db.add(q)
    db.commit()
    db.refresh(q)
    return query_to_dict(q)


@router.delete("/visibility/queries/{query_id}")
def delete_query(query_id: UUID, db: Session = Depends(get_db)):
    q = db.get(VisibilityQuery, query_id)
    if not q:
        raise HTTPException(404, "Query not found")
    q.active = False
    db.commit()
    return {"deleted": True}


@router.post("/visibility/queries/suggest")
def suggest_queries(body: SuggestRequest | None = None, db: Session = Depends(get_db)):
    """Seed buyer-style queries from the domains we can win."""
    body = body or SuggestRequest()
    existing = {q.query.lower() for q in db.query(VisibilityQuery).filter(VisibilityQuery.active.is_(True)).all()}
    added = []
    for domain in go_domains()[:6]:
        candidates = _template_queries(domain)
        if llm_available():
            try:
                data = chat_json(
                    f"Write {body.per_domain} short questions a buyer would type into ChatGPT when looking for "
                    f"a vendor or development partner for: {domain}. Natural phrasing, no brand names. "
                    'Output JSON: {"queries": [str]}'
                )
                candidates = [str(x) for x in data.get("queries") or []] or candidates
            except Exception:  # noqa: BLE001
                pass
        for text in candidates[: body.per_domain]:
            if text.lower() in existing:
                continue
            q = VisibilityQuery(query=text, domain=domain)
            db.add(q)
            existing.add(text.lower())
            added.append(text)
    db.commit()
    return {"added": added}


@router.post("/visibility/check")
def check_endpoint(db: Session = Depends(get_db)):
    job = create_job(db, "visibility_check")
    run_job_in_thread(job.id, lambda s, _r: run_checks(s))
    return {"job_id": str(job.id)}


@router.get("/visibility/summary")
def summary(db: Session = Depends(get_db)):
    checks = _latest_checks(db)
    competitor_counts = Counter(c for check in checks for c in (check.competitors or []))
    ranks = [c.rank for c in checks if c.rank]
    by_provider: dict[str, dict] = {}
    for c in checks:
        p = by_provider.setdefault(c.provider, {"checks": 0, "mentioned": 0})
        p["checks"] += 1
        p["mentioned"] += int(bool(c.mentioned))
    return {
        "company": settings.default_company_name,
        "providers": [p for p, _, _ in providers()],
        "share": latest_share(db),
        "avg_rank": round(sum(ranks) / len(ranks), 1) if ranks else None,
        "by_provider": by_provider,
        "top_competitors": [{"name": n, "mentions": k} for n, k in competitor_counts.most_common(10)],
        "latest": [check_to_dict(c) for c in sorted(checks, key=lambda c: (c.query or "", c.provider))],
    }


@router.get("/visibility/trend")
def trend(days: int = 90, db: Session = Depends(get_db)):
    since = datetime.utcnow() - timedelta(days=max(1, min(days, 365)))
    buckets: dict[tuple[str, str], list[int]] = {}
    for c in db.query(VisibilityCheck).filter(VisibilityCheck.checked_at >= since).all():
        key = (c.checked_at.date().isoformat(), c.provider)
        buckets.setdefault(key, []).append(int(bool(c.mentioned)))
    points = [
        {"date": d, "provider": p, "share": round(sum(v) / len(v), 3), "checks": len(v)}
        for (d, p), v in sorted(buckets.items())
    ]
    return {"points": points}


@router.post("/visibility/recommendations")
def recommendations(db: Session = Depends(get_db)):
    checks = _latest_checks(db)
    if not checks:
        raise HTTPException(400, "Run a visibility check first")
    missing = [c for c in checks if not c.mentioned]
    if not llm_available():
        top = Counter(x for c in missing for x in (c.competitors or [])).most_common(3)
        return {"recommendations": [
            {
                "title": f"Publish a '{settings.default_company_name} vs {name}' comparison page",
                "why": f"{name} is named in {count} answers where you are missing.",
                "target_queries": [c.query for c in missing if name in (c.competitors or [])][:3],
                "format": "comparison page",
            }
            for name, count in top
        ]}
    data = [
        {"query": c.query, "provider": c.provider, "mentioned": c.mentioned, "rank": c.rank,
         "competitors": (c.competitors or [])[:6]}
        for c in checks
    ]
    prompt = RECOMMEND_PROMPT.format(
        company=settings.default_company_name, url=settings.default_company_url,
        data=json.dumps(data, indent=1),
    )
    return {"recommendations": chat_json(prompt).get("recommendations") or []}
