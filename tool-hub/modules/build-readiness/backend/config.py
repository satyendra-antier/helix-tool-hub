from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://toolhub:toolhub@postgres:5432/toolhub"
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    embedding_model: str = "text-embedding-3-small"
    default_company_url: str = "https://www.antier.com/"
    default_company_name: str = "Antier"
    max_crawl_pages: int = 50
    chunk_size: int = 900
    chunk_overlap: int = 120
    market_depth_api_url: str = "http://market-depth-api:8002"

    class Config:
        env_file = ".env"


settings = Settings()
