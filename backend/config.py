"""
PRIME OS — configuration.

Values are read from environment variables or a .env file at the repo root.
Required:  ANTHROPIC_API_KEY
Optional:  DATABASE_URL  (default: local postgres)
           PRIME_PORT    (default: 7474)
           PRIME_HOST    (default: 127.0.0.1)
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",   # no env_prefix — reads DATABASE_URL, ANTHROPIC_API_KEY directly
    )

    # Anthropic
    anthropic_api_key: str = ""

    # PostgreSQL connection URL
    database_url: str = "postgresql+asyncpg://prime:prime_dev@localhost:5432/prime"

    # Server
    prime_host: str = "127.0.0.1"
    prime_port: int = 7474

    # CORS
    cors_origins: list[str] = ["*"]

    @property
    def host(self) -> str:
        return self.prime_host

    @property
    def port(self) -> int:
        return self.prime_port


settings = Settings()
