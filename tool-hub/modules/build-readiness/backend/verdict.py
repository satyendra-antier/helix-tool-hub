"""LLM verdict synthesis — grounded in RAG chunks + market depth data."""

from __future__ import annotations

import json
import re

from config import settings
from llm_client import chat, parse_json


VERDICT_PROMPT = """You are a CTO advisor for a services company evaluating whether to build/sell a product in a market domain.

You receive:
1. MARKET DATA — demand score, hiring, capital, product types, revenue models (from live market signals)
2. COMPANY EVIDENCE — retrieved chunks from the company's indexed website/videos
3. CAPABILITY MATCH — algorithmic scores and matched skills

Rules:
- verdict must be GO, CONDITIONAL, or NO_GO
- can_build must reflect whether the company has demonstrated depth in retrieved evidence
- market_need must cite market_score and demand signals from input only
- our_strengths and gaps must cite company evidence chunks only
- how_to_build must be a practical phased plan (discovery → MVP → GTM) using existing strengths
- revenue_path must align with market revenue_models in input
- For NO_GO verdicts: strengthen_suggestions is REQUIRED — 3–5 specific, actionable steps to build credibility and depth in this field (case studies, hires, certifications, productized offerings, partnerships, content, open-source). Each suggestion must be concrete and tied to gaps identified.
- For CONDITIONAL verdicts: include strengthen_suggestions with 2–3 steps to move from conditional to GO
- NEVER invent numbers not in input JSON
- NEVER claim capabilities not supported by company_evidence excerpts

Output JSON:
{
  "verdict": "GO" | "CONDITIONAL" | "NO_GO",
  "can_build": boolean,
  "confidence": "high" | "medium" | "low",
  "headline": string,
  "market_need": string,
  "our_strengths": string[],
  "gaps": string[],
  "strengthen_suggestions": string[],
  "how_to_build": { "phase_1": string, "phase_2": string, "phase_3": string },
  "revenue_path": string,
  "depth_assessment": string,
  "cited_evidence": [{ "url": string, "excerpt": string }]
}"""


def _normalize_number_token(raw: str) -> str | None:
    token = raw.replace(",", "").strip().rstrip(".")
    if not token:
        return None
    try:
        float(token)
    except ValueError:
        return None
    return token


def _extract_numbers(text: str) -> set[str]:
    found = set()
    for match in re.findall(r"\d[\d,.]*", text):
        normalized = _normalize_number_token(match)
        if normalized:
            found.add(normalized)
    return found


def validate_verdict(input_data: dict, output: dict) -> tuple[bool, str]:
    input_nums = _extract_numbers(json.dumps(input_data))
    out_text = json.dumps(output)
    out_nums = _extract_numbers(out_text)
    invented = []
    for n in out_nums:
        if n in input_nums:
            continue
        try:
            if float(n) > 5:
                invented.append(n)
        except ValueError:
            continue
    if invented:
        return False, f"Possible invented numbers: {invented[:5]}"
    if output.get("verdict") not in ("GO", "CONDITIONAL", "NO_GO"):
        return False, "Invalid verdict value"
    return True, "Validation passed"


def generate_verdict(
    domain_data: dict,
    capability_score: float,
    matched_capabilities: list[str],
    retrieved_chunks: list[dict],
    retry_note: str = "",
) -> tuple[dict, bool, str]:
    if not settings.resolve_api_key():
        verdict = "CONDITIONAL" if capability_score >= 40 else "NO_GO"
        domain = domain_data.get("domain_name", "this domain")
        strengthen = []
        if verdict == "NO_GO":
            strengthen = [
                f"Publish 2–3 in-depth case studies on {domain} with measurable outcomes",
                f"Hire or upskill a dedicated {domain} practice lead and list them on your site",
                f"Ship a small productized {domain} offering (audit, starter kit, or managed service)",
                "Add client logos, certifications, and technical blog posts targeting this domain",
                "Partner with a domain specialist firm and co-deliver one pilot project",
            ]
        elif verdict == "CONDITIONAL":
            strengthen = [
                f"Expand {domain} content on your website with technical depth and client proof",
                f"Launch a focused landing page and lead magnet for {domain}",
            ]
        return {
            "verdict": verdict,
            "can_build": capability_score >= 50,
            "confidence": "low",
            "headline": f"Capability match {capability_score}/100 — configure OPENAI_API_KEY for full analysis",
            "market_need": domain_data.get("product_landscape", {}).get("demand_summary", "Run Market Depth refresh"),
            "our_strengths": matched_capabilities[:5],
            "gaps": (
                ["Insufficient demonstrated depth — see strengthen suggestions"]
                if verdict == "NO_GO"
                else ["Depth signals present but need richer evidence"]
            ),
            "strengthen_suggestions": strengthen,
            "how_to_build": {
                "phase_1": "Validate demand with Market Depth signals",
                "phase_2": "Map company capabilities to product type",
                "phase_3": "Pilot with existing service line",
            },
            "revenue_path": "Align with top revenue model from market landscape",
            "depth_assessment": f"Algorithmic capability score: {capability_score}/100",
            "cited_evidence": [
                {"url": c.get("source_url", ""), "excerpt": (c.get("content", "")[:200])}
                for c in retrieved_chunks[:3]
            ],
        }, False, "OPENAI_API_KEY not set"

    evidence = [
        {
            "url": c.get("source_url", ""),
            "title": c.get("title", ""),
            "excerpt": c.get("content", "")[:500],
            "similarity": c.get("similarity"),
        }
        for c in retrieved_chunks
    ]

    input_data = {
        "domain": domain_data.get("domain_name"),
        "track": domain_data.get("track"),
        "market_score": domain_data.get("market_score"),
        "capability_score": capability_score,
        "matched_capabilities": matched_capabilities,
        "market_landscape": domain_data.get("product_landscape", {}),
        "market_components": domain_data.get("components", {}),
        "company_evidence": evidence,
    }

    prompt = f"{VERDICT_PROMPT}\n\nInput:\n{json.dumps(input_data, indent=2)}"
    if retry_note:
        prompt += f"\n\nCORRECTION: {retry_note}"

    output = parse_json(chat(prompt, json_mode=True))
    passed, notes = validate_verdict(input_data, output)

    if not passed:
        output = parse_json(chat(f"{prompt}\n\nRetry — {notes}", json_mode=True))
        passed, notes = validate_verdict(input_data, output)

    return output, passed, notes


def ensure_strengthen_suggestions(output: dict, domain_name: str) -> dict:
    """Guarantee actionable suggestions for NO_GO / CONDITIONAL even if LLM omits them."""
    verdict = output.get("verdict")
    if verdict not in ("NO_GO", "CONDITIONAL"):
        return output
    if output.get("strengthen_suggestions"):
        return output

    domain = domain_name or "this domain"
    gaps = output.get("gaps") or []
    if verdict == "NO_GO":
        suggestions = [
            f"Publish 2–3 in-depth case studies demonstrating {domain} delivery with metrics",
            f"Hire or showcase a dedicated {domain} practice lead on your website",
            f"Ship a productized {domain} offering (audit, starter kit, or managed service)",
            "Add client logos, certifications, and technical content targeting this domain",
        ]
        suggestions.extend(f"Close gap: {g}" for g in gaps[:2])
        output["strengthen_suggestions"] = suggestions[:5]
    else:
        output["strengthen_suggestions"] = [
            f"Expand {domain} proof on your site — case studies, team bios, and technical blogs",
            f"Launch a focused landing page and lead magnet for {domain}",
            *(f"Address: {g}" for g in gaps[:1]),
        ][:4]
    return output


def compute_verdict_label(market_score: float, capability_score: float) -> str:
    opportunity = market_score * 0.55 + capability_score * 0.45
    if opportunity >= 65 and capability_score >= 45:
        return "GO"
    if opportunity >= 45 and capability_score >= 30:
        return "CONDITIONAL"
    return "NO_GO"
