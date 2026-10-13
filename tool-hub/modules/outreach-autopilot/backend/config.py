from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql://toolhub:toolhub@postgres:5432/toolhub"
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    outreach_openai_api_key: str = ""
    outreach_openai_model: str = ""

    lead_intelligence_api_url: str = "http://lead-intelligence-api:8003"
    growth_pillars_api_url: str = "http://growth-pillars-api:8005"

    # Encrypts mailbox passwords at rest. Falls back to NEXTAUTH_SECRET.
    outreach_secret_key: str = ""
    nextauth_secret: str = ""

    # Public URL of this service, used in unsubscribe links inside emails.
    outreach_public_url: str = "http://localhost:8106"
    heartbeat_minutes: float = 15.0
    http_timeout_seconds: float = 20.0

    default_company_name: str = "Antier"
    default_company_url: str = "https://www.antier.com/"

    # Alerts and CRM (Phase 3). All optional.
    slack_webhook_url: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    hubspot_access_token: str = ""
    twenty_api_url: str = ""
    twenty_api_key: str = ""

    # AI calls through a self-hosted Dograh instance (Phase 5). All optional.
    dograh_api_url: str = ""
    dograh_api_key: str = ""
    dograh_workflow_id: str = ""

    def resolve_api_key(self) -> str:
        return self.outreach_openai_api_key or self.openai_api_key

    def resolve_chat_model(self) -> str:
        return self.outreach_openai_model or self.openai_model


settings = Settings()
