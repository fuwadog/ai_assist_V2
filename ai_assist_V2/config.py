"""Configuration management for AI Assistant CLI V2."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env.local first, then .env as fallback
_env_path = Path(__file__).parent / ".env.local"
if _env_path.exists():
    load_dotenv(_env_path)
else:
    load_dotenv()


@dataclass
class Config:
    """All runtime configuration loaded from environment variables."""

    # API
    nvidia_api_key: str = field(default_factory=lambda: os.getenv("NVIDIA_API_KEY", ""))
    base_url: str = field(
        default_factory=lambda: os.getenv(
            "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
        )
    )
    default_model: str = field(
        default_factory=lambda: os.getenv(
            "DEFAULT_MODEL", "meta/llama-3.1-405b-instruct"
        )
    )

    # Context
    max_context_tokens: int = field(
        default_factory=lambda: int(os.getenv("MAX_CONTEXT_TOKENS", "7000"))
    )
    cache_enabled: bool = field(
        default_factory=lambda: os.getenv("CACHE_ENABLED", "true").lower() == "true"
    )
    cache_ttl: int = field(
        default_factory=lambda: int(os.getenv("CACHE_TTL", "3600"))
    )

    # Logging
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper()
    )

    # Database
    db_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("DB_PATH", "data/ai_assistant.db")
        )
    )

    # RLM (Phase 3 — not used yet, kept for forward compat)
    rlm_max_iterations: int = field(
        default_factory=lambda: int(os.getenv("RLM_MAX_ITERATIONS", "10"))
    )
    rlm_timeout: int = field(
        default_factory=lambda: int(os.getenv("RLM_TIMEOUT", "300"))
    )
    rlm_enable_dedup: bool = field(
        default_factory=lambda: os.getenv("RLM_ENABLE_DEDUP", "true").lower() == "true"
    )
    rlm_fallback_enabled: bool = field(
        default_factory=lambda: os.getenv("RLM_FALLBACK_ENABLED", "true").lower() == "true"
    )

    def validate(self) -> None:
        """Raise ValueError for critical missing config."""
        if not self.nvidia_api_key:
            raise ValueError(
                "NVIDIA_API_KEY is not set. "
                "Create a .env.local file with your API key. "
                "Get a free key at https://build.nvidia.com/"
            )


# Singleton instance
_config: Config | None = None


def get_config() -> Config:
    """Return the global Config singleton."""
    global _config
    if _config is None:
        _config = Config()
    return _config
