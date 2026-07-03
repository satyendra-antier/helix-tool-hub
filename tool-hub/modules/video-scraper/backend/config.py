from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://toolhub:toolhub@postgres:5432/toolhub"
    redis_url: str = "redis://redis:6379/0"
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    transcription_provider: str = "openai"
    max_video_duration_seconds: int = 7200
    rate_limit_per_domain_seconds: float = 1.0
    ignore_robots_txt: bool = False
    media_dir: str = "/app/media"

    class Config:
        env_file = ".env"


settings = Settings()
