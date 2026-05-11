"""
PRIME OS — configuration.

Values are read from environment variables or a .env file at the repo root.

LLM (pick one provider):
  Claude   — set ANTHROPIC_API_KEY  (default model: claude-haiku-4-5-20251001)
  OpenAI   — set OPENAI_API_KEY and LLM_MODEL=gpt-4o-mini
  Ollama   — set LLM_MODEL=ollama/llama3.2 and LLM_API_BASE=http://localhost:11434
  vLLM     — set LLM_MODEL=openai/mistral-7b and LLM_API_BASE=http://localhost:8000/v1

Other:
  DATABASE_URL  (default: local postgres)
  PRIME_PORT    (default: 7474)
  PRIME_HOST    (default: 127.0.0.1)
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM ────────────────────────────────────────────────────────────────────
    # Model string passed directly to LiteLLM — prefix selects the provider.
    # Examples: "claude-haiku-4-5-20251001", "gpt-4o-mini", "ollama/llama3.2"
    llm_model: str = "claude-haiku-4-5-20251001"

    # Optional base URL for local/self-hosted models (Ollama, vLLM, LM Studio).
    # Leave empty to use the provider's default endpoint.
    llm_api_base: str = ""

    # Provider API keys — LiteLLM picks the right one based on llm_model.
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # ── Database ───────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://prime:prime_dev@localhost:5432/prime"

    # ── Server ─────────────────────────────────────────────────────────────────
    prime_host: str = "127.0.0.1"
    prime_port: int = 7474

    # ── CORS ───────────────────────────────────────────────────────────────────
    cors_origins: list[str] = ["*"]

    # ── Derived ────────────────────────────────────────────────────────────────

    @property
    def host(self) -> str:
        return self.prime_host

    @property
    def port(self) -> int:
        return self.prime_port

    @property
    def llm_ready(self) -> bool:
        """
        True when the configured LLM can be called without an auth error.
        Local models (ollama/vllm) are always considered ready.
        Cloud providers require their respective API key.
        """
        m = self.llm_model.lower()
        if m.startswith("ollama/") or m.startswith("vllm/"):
            return True
        if "claude" in m:
            return bool(self.anthropic_api_key)
        if "gpt" in m or m.startswith("openai/"):
            return bool(self.openai_api_key)
        # Unknown provider — assume ready and let LiteLLM raise if not.
        return True


settings = Settings()
