from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    anthropic_auth_token: str = ""
    llm_base_url: str = "https://ai-coding-ali.deeproute.cn/v1"
    llm_model: str = "glm-5.1"
    llm_timeout: int = 120
    llm_max_tokens: int = 4096

    # SMTP
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    recipient_email: str = ""

    # Web
    web_base_url: str = "http://localhost:8080"
    web_host: str = "0.0.0.0"
    web_port: int = 8080

    # Podcast Index
    podcast_index_key: str = ""
    podcast_index_secret: str = ""

    # Schedule
    digest_cron_hour: int = 2
    digest_cron_minute: int = 0
    email_send_hour: int = 7
    email_send_minute: int = 0

    # ASR
    whisper_model: str = "large-v3"
    whisper_device: str = "cuda"

    # Database
    db_path: str = "data/content_digest.db"


settings = Settings()
