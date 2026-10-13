import json
from openai import OpenAI
from config import settings


def llm_available() -> bool:
    return bool(settings.resolve_api_key())


def chat(prompt: str, *, json_mode: bool = False, system: str | None = None) -> str:
    key = settings.resolve_api_key()
    if not key:
        raise ValueError("OUTREACH_OPENAI_API_KEY or OPENAI_API_KEY required")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    kwargs: dict = {"model": settings.resolve_chat_model(), "messages": messages}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = OpenAI(api_key=key).chat.completions.create(**kwargs)
    text = (response.choices[0].message.content or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return text


def chat_json(prompt: str, *, system: str | None = None) -> dict:
    return json.loads(chat(prompt, json_mode=True, system=system))
