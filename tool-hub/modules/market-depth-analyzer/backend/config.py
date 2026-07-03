from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://toolhub:toolhub@postgres:5432/toolhub"
    redis_url: str = "redis://redis:6379/0"
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    github_token: str = ""
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
