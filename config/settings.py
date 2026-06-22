from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    anthropic_api_key: str
    github_token: str
    github_webhook_secret: str = "dev-secret"
    chroma_path: str = "./chroma_db"
    app_port: int = 8000
    claude_model: str = "claude-sonnet-4-6"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
