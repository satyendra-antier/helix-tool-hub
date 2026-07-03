import json
import re
from config import settings
from llm_client import chat, parse_json


NARRATIVE_PROMPT = """You are a market analyst for a technical CEO. You receive computed domain scores,
raw evidence, AND a product_landscape object per domain (product types in demand, builders,
revenue models, market indicators).

You must:
1. Write a 2-3 sentence executive summary ranking the top domains BY PRODUCT/BUSINESS opportunity,
   not just engineering skill demand.
2. For each of the top 3 domains, write one paragraph covering:
   - WHAT product types are in demand (from product_types_in_demand)
   - WHO is building (from builders — cite real names from input)
   - HOW money is made (from revenue_models — cite derived_from product types)
   - Market size signals (from market_indicators — only cite numbers present in input)
3. You are FORBIDDEN from stating any number not present in the input JSON.
4. You are FORBIDDEN from ranking domains differently than composite_score ordering.
5. Flag thin evidence explicitly when signals_available < 3.

Output valid JSON:
{
  "executive_summary": string,
  "domain_narratives": [{
    "domain": string,
    "narrative": string,
    "product_focus": string,
    "cited_metrics": string[]
  }],
  "confidence_flags": [{ "domain": string, "reason": string }]
}"""


def _serialize_scores(scores: list, landscapes: dict | None = None) -> dict:
    landscapes = landscapes or {}
    return {
        "domains": [
            {
                "domain": s.domain,
                "track": s.track,
                "composite_score": s.composite_score,
                "components": s.components,
                "raw_evidence": {
                    k: {
                        "value": v.value,
                        "unit": v.unit,
                        "available": v.available,
                        "raw_data": v.raw_data,
                        "note": v.note,
                    }
                    for k, v in s.raw_evidence.items()
                },
                "product_landscape": landscapes.get(s.domain_id, landscapes.get(str(s.domain_id), {})),
                "sources_available": sum(
                    1 for v in s.raw_evidence.values() if v.available
                ),
            }
            for s in scores
        ]
    }


def _extract_numbers(text: str) -> set[str]:
    """Extract numeric tokens, normalizing formats like 1,234.56."""
    found = set()
    for match in re.findall(r"\d[\d,.]*", text):
        normalized = match.replace(",", "")
        found.add(normalized)
        try:
            val = float(normalized)
            if val == int(val):
                found.add(str(int(val)))
        except ValueError:
            pass
    return found


def validate_narrative(input_data: dict, output: dict) -> tuple[bool, str]:
    input_json = json.dumps(input_data)
    numbers_in_input = _extract_numbers(input_json)

    cited = []
    for narrative in output.get("domain_narratives", []):
        cited.extend(narrative.get("cited_metrics", []))
        cited.append(narrative.get("narrative", ""))
    cited_text = " ".join(cited) + " " + output.get("executive_summary", "")
    numbers_in_output = _extract_numbers(cited_text)

    invented = []
    for num in numbers_in_output:
        if num not in numbers_in_input:
            try:
                if float(num) > 1:
                    invented.append(num)
            except ValueError:
                invented.append(num)

    if invented:
        return False, f"Invented numbers detected: {invented[:5]}"

    ranked = sorted(
        input_data.get("domains", []),
        key=lambda d: d.get("composite_score", 0),
        reverse=True,
    )
    top_names = [d["domain"] for d in ranked[:3]]
    narrative_domains = [n["domain"] for n in output.get("domain_narratives", [])]
    for nd in narrative_domains:
        if nd not in top_names:
            return False, f"Narrative domain '{nd}' not in top 3 by composite_score"

    if len(narrative_domains) != len(set(narrative_domains)):
        return False, "Duplicate domains in domain_narratives"

    return True, "Validation passed"


def generate_narrative(
    scores: list,
    landscapes: dict | None = None,
    retry_note: str = "",
) -> tuple[dict, bool, str]:
    if not settings.openai_api_key:
        ranked = sorted(scores, key=lambda s: s.composite_score, reverse=True)
        return {
            "executive_summary": (
                "Scores computed deterministically from live market signals. "
                f"Top domain: {ranked[0].domain} ({ranked[0].composite_score}/100). "
                "Configure OPENAI_API_KEY for AI narrative synthesis."
            ),
            "domain_narratives": [],
            "confidence_flags": [{"domain": "all", "reason": "No narrative — missing API key"}],
        }, False, "OPENAI_API_KEY not set"

    input_data = _serialize_scores(scores, landscapes)
    prompt = f"{NARRATIVE_PROMPT}\n\nInput data:\n{json.dumps(input_data, indent=2)}"
    if retry_note:
        prompt += f"\n\nCORRECTION: {retry_note}"

    text = chat(prompt, json_mode=True)
    output = parse_json(text)
    passed, notes = validate_narrative(input_data, output)

    if not passed:
        retry_prompt = f"Your previous response failed validation: {notes}. Only cite numbers from the input."
        text2 = chat(f"{prompt}\n\n{retry_prompt}", json_mode=True)
        output = parse_json(text2)
        passed, notes = validate_narrative(input_data, output)

    return output, passed, notes
