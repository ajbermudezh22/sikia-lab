"""Runtime configuration.

Everything has a default that works with no credentials, so the whole system runs
and tests green on a fresh clone. `SIKIA_PROVIDER_MODE=live` opts into real calls.
"""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SIKIA_", env_file=".env", extra="ignore")

    provider_mode: Literal["fake", "live"] = "fake"

    # Per-call ceiling. Clinical dictation is interactive: a slow answer is a wrong
    # answer, so we would rather fail over than wait.
    call_timeout_s: float = 3.0

    # Consecutive failures before a provider is taken out of rotation.
    breaker_threshold: int = 3

    # How long a tripped breaker stays open before one probe request is allowed.
    breaker_cooldown_s: float = 15.0

    # Audio framing for the websocket ingest path.
    sample_rate_hz: int = 16_000
    chunk_ms: int = 320

    @property
    def bytes_per_chunk(self) -> int:
        """16-bit mono PCM."""
        return int(self.sample_rate_hz * (self.chunk_ms / 1000) * 2)


settings = Settings()
