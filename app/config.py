"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    """Immutable application settings."""

    # Server
    host: str = field(default_factory=lambda: os.getenv("GRIDWISE_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("GRIDWISE_PORT", "8000")))

    # LLM provider (OpenAI-compatible API)
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_base_url: str = field(
        default_factory=lambda: os.getenv(
            "LLM_BASE_URL", "https://api.openai.com/v1"
        )
    )
    llm_model: str = field(
        default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o-mini")
    )
    llm_temperature: float = field(
        default_factory=lambda: float(os.getenv("LLM_TEMPERATURE", "0.0"))
    )
    llm_max_tokens: int = field(
        default_factory=lambda: int(os.getenv("LLM_MAX_TOKENS", "2048"))
    )
    llm_timeout: int = field(
        default_factory=lambda: int(os.getenv("LLM_TIMEOUT", "30"))
    )

    # Optimizer
    optimizer_timeout: int = field(
        default_factory=lambda: int(os.getenv("OPTIMIZER_TIMEOUT", "30"))
    )

    # Numeric tolerance for comparisons
    tolerance_kwh: float = 0.01
    tolerance_bdt: float = 0.01


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the singleton settings instance (cached)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
