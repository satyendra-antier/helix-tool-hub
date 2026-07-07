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
    build_readiness_openai_api_key: str = ""
    build_readiness_openai_model: str = ""
    embedding_model: str = "text-embedding-3-small"
    default_company_url: str = "https://www.antier.com/"
    default_company_name: str = "Antier"
    max_crawl_pages: int = 50
    chunk_size: int = 900
    chunk_overlap: int = 120
    market_depth_api_url: str = "http://market-depth-api:8002"

    def resolve_api_key(self) -> str:
        return self.build_readiness_openai_api_key or self.openai_api_key

    def resolve_chat_model(self) -> str:
        return self.build_readiness_openai_model or self.openai_model


settings = Settings()
