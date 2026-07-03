import json
from config import settings
from llm_client import chat, parse_json

OUTREACH_PROMPT = """You are drafting a first-outreach message. You will receive a JSON object with the
entity's real signal data and the sender's positioning. Rules:

1. Reference the SPECIFIC signal that makes this lead relevant right now
   (e.g. "saw your Series A raise" / "saw the tender for X" / "saw you're hiring
   for smart contract auditors") — never write a generic template.
2. Do not fabricate any detail about the company not present in the input.
3. Keep it under 120 words, one clear ask, no hype language.
4. Output JSON: { "subject": string, "body": string, "cited_signal": string }

The output is a DRAFT for human review — it will never be sent automatically."""


def generate_outreach_draft(entity: dict, contacts: list[dict]) -> dict:
    if not settings.openai_api_key:
        signal = entity.get("signal_type", "opportunity")
        return {
            "subject": f"Re: {entity.get('name', 'your project')}",
            "body": f"I noticed your recent {signal} and thought there might be a fit. Happy to share how we've helped similar teams — would a brief call work?",
            "cited_signal": entity.get("description", "")[:100],
        }

    input_data = {
        "entity": entity,
        "contacts": contacts,
        "positioning_keywords": [
            "blockchain security", "smart contract audit", "AI agent architecture",
        ],
    }
    return parse_json(
        chat(f"{OUTREACH_PROMPT}\n\nInput:\n{json.dumps(input_data, default=str)}", json_mode=True)
    )
