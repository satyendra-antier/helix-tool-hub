from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql://toolhub:toolhub@postgres:5432/toolhub"
    redis_url: str = "redis://redis:6379/0"
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    lead_intelligence_openai_api_key: str = ""
    lead_intelligence_openai_model: str = ""
    apollo_api_key: str = ""
    hunter_api_key: str = ""
    clearbit_api_key: str = ""
    sam_gov_api_key: str = ""
    crunchbase_api_key: str = ""
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    rate_limit_seconds: float = 1.0

    def resolve_api_key(self) -> str:
        return self.lead_intelligence_openai_api_key or self.openai_api_key

    def resolve_chat_model(self) -> str:
        return self.lead_intelligence_openai_model or self.openai_model


settings = Settings()
