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
    market_depth_openai_api_key: str = ""
    market_depth_openai_model: str = ""
    github_token: str = ""
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""

    def resolve_api_key(self) -> str:
        return self.market_depth_openai_api_key or self.openai_api_key

    def resolve_chat_model(self) -> str:
        return self.market_depth_openai_model or self.openai_model


settings = Settings()
