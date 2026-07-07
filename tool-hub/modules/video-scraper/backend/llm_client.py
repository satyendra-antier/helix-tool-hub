import json
from openai import OpenAI
from config import settings


def get_client() -> OpenAI:
    key = settings.resolve_api_key()
    if not key:
        raise ValueError(
            "VIDEO_SCRAPER_OPENAI_API_KEY or OPENAI_API_KEY required for video scraper"
        )
    return OpenAI(api_key=key)


def chat(prompt: str, *, json_mode: bool = False) -> str:
    kwargs: dict = {
        "model": settings.resolve_chat_model(),
        "messages": [{"role": "user", "content": prompt}],
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = get_client().chat.completions.create(**kwargs)
    text = (response.choices[0].message.content or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return text


def parse_json(text: str) -> dict:
    return json.loads(text)
