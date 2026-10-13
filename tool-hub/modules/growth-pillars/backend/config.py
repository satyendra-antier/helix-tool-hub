from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql://toolhub:toolhub@postgres:5432/toolhub"
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    growth_pillars_openai_api_key: str = ""
    growth_pillars_openai_model: str = ""
    perplexity_api_key: str = ""
    perplexity_model: str = "sonar"
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""

    lead_intelligence_api_url: str = "http://lead-intelligence-api:8003"
    market_depth_api_url: str = "http://market-depth-api:8002"
    build_readiness_api_url: str = "http://build-readiness-api:8004"
    outreach_api_url: str = "http://outreach-autopilot-api:8006"

    default_company_name: str = "Antier"
    default_company_url: str = "https://www.antier.com/"

    insider_scan_interval_hours: float = 24.0
    http_timeout_seconds: float = 20.0

    def resolve_api_key(self) -> str:
        return self.growth_pillars_openai_api_key or self.openai_api_key

    def resolve_chat_model(self) -> str:
        return self.growth_pillars_openai_model or self.openai_model


settings = Settings()
