from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://toolhub:toolhub@postgres:5432/toolhub"
    redis_url: str = "redis://redis:6379/0"
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    apollo_api_key: str = ""
    hunter_api_key: str = ""
    clearbit_api_key: str = ""
    sam_gov_api_key: str = ""
    crunchbase_api_key: str = ""
    rate_limit_seconds: float = 1.0

    class Config:
        env_file = ".env"


settings = Settings()
