"""
PRIME OS — configuration.

Values are read from environment variables or a .env file at the repo root.
Required:  ANTHROPIC_API_KEY
Optional:  PRIME_WORKSPACE  (default: ~/PRIME)
           PRIME_PORT       (default: 7474)
           PRIME_HOST       (default: 127.0.0.1)
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Anthropic
    anthropic_api_key: str = ""

    # Workspace root — where all PRIME data is stored
    workspace: str = str(Path.home() / "PRIME")

    # Server
    host: str = "127.0.0.1"
    port: int = 7474

    # CORS origins to allow (the HTML prototype during dev)
    cors_origins: list[str] = ["*"]

    @property
    def workspace_path(self) -> Path:
        p = Path(self.workspace).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    class Config:
        env_prefix = "PRIME_"


settings = Settings()
