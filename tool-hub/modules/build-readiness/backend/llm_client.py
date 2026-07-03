import json
from openai import OpenAI
from config import settings


def get_client() -> OpenAI:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY required")
    return OpenAI(api_key=settings.openai_api_key)


def chat(prompt: str, *, json_mode: bool = False) -> str:
    kwargs: dict = {
        "model": settings.openai_model,
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


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    client = get_client()
    response = client.embeddings.create(
        model=settings.embedding_model,
        input=texts,
    )
    return [item.embedding for item in response.data]
