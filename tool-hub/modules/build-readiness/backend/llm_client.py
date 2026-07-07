from openai import OpenAI
from config import settings


def get_client() -> OpenAI:
    key = settings.resolve_api_key()
    if not key:
        raise ValueError("BUILD_READINESS_OPENAI_API_KEY or OPENAI_API_KEY required")
    return OpenAI(api_key=key, timeout=120.0, max_retries=2)


def chat(prompt: str, *, json_mode: bool = False) -> str:
    kwargs: dict = {
        "model": settings.resolve_chat_model(),
        "messages": [{"role": "user", "content": prompt}],
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = get_client().chat.completions.create(**kwargs)
    return (response.choices[0].message.content or "").strip()


def parse_json(text: str) -> dict:
    import json
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    response = get_client().embeddings.create(
        model=settings.embedding_model,
        input=texts,
    )
    return [item.embedding for item in response.data]
