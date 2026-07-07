from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql://toolhub:toolhub@postgres:5432/toolhub"
    redis_url: str = "redis://redis:6379/0"

    # Shared hub fallback
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"

    # Video Scraper — dedicated credentials (override shared hub key)
    video_scraper_openai_api_key: str = ""
    video_scraper_openai_model: str = ""
    # local = on-device faster-whisper (no OpenAI Audio API); openai = whisper/transcribe API
    transcription_provider: str = "local"
    transcription_model: str = "whisper-1"
    local_whisper_model: str = "small"
    local_whisper_device: str = "cpu"
    local_whisper_compute_type: str = "int8"

    max_video_duration_seconds: int = 7200
    max_videos_per_page: int = 25
    rate_limit_per_domain_seconds: float = 1.0
    ignore_robots_txt: bool = False
    video_discovery_ignore_robots: bool = True
    media_dir: str = "/app/media"
    minio_enabled: bool = True
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "toolhub"
    minio_secret_key: str = "toolhubsecret"
    minio_bucket: str = "video-scraper-temp"
    minio_secure: bool = False

    def resolve_api_key(self) -> str:
        return self.video_scraper_openai_api_key or self.openai_api_key

    def resolve_chat_model(self) -> str:
        return self.video_scraper_openai_model or self.openai_model

    def using_dedicated_key(self) -> bool:
        return bool(self.video_scraper_openai_api_key)


settings = Settings()
