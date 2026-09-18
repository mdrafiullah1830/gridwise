"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _parse_cors(origins_raw: str) -> list[str]:
    """Parse a comma-separated CORS allowlist. '*' returns literal wildcard."""
    origins_raw = origins_raw.strip()
    if origins_raw == "" or origins_raw == "*":
        return ["*"]
    return [o.strip() for o in origins_raw.split(",") if o.strip()]


@dataclass(frozen=True)
class Settings:
    """Immutable application settings."""

    # Server
    host: str = field(default_factory=lambda: os.getenv("GRIDWISE_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("GRIDWISE_PORT", "8000")))

    # CORS — comma-separated allowlist. Use "*" for fully permissive (dev only).
    cors_allow_origins: list[str] = field(
        default_factory=lambda: _parse_cors(
            os.getenv("GRIDWISE_CORS_ORIGINS", "*")
        )
    )
    cors_allow_credentials: bool = field(
        default_factory=lambda: os.getenv("GRIDWISE_CORS_CREDENTIALS", "false").lower()
        in ("1", "true", "yes")
    )

    # Samples file location (overridable for local dev).
    # Falls back to a bundled copy inside the package.
    samples_file: str = field(
        default_factory=lambda: os.getenv(
            "GRIDWISE_SAMPLES_FILE",
            str(Path(__file__).resolve().parent.parent / "samples" / "sample_cases.json"),
        )
    )

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
