from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Vision Assistant"
    database_path: Path = Path("data/vision_assistant.sqlite3")
    upload_dir: Path = Path("data/uploads")
    keyframe_dir: Path = Path("data/keyframes")
    vision_mock_mode: bool = True
    frame_sample_seconds: float = 1.5
    alert_cooldown_seconds: int = 20
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str = "gpt-4.1-mini"
    vlm_base_url: str | None = None
    vlm_api_key: str | None = None
    vlm_model: str = "qwen-vl"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.keyframe_dir.mkdir(parents=True, exist_ok=True)
    return settings

