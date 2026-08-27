"""The contract every provider implements.

Deliberately narrow: the router only needs a name, a priority, and a coroutine that
either returns a result or raises. Everything else — auth, retries inside the SDK,
response shape — is the adapter's problem, not the router's.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class Transcript(BaseModel):
    text: str
    confidence: float
    provider: str
    is_final: bool = False


class Completion(BaseModel):
    text: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0


class ProviderError(RuntimeError):
    """Raised by an adapter when a call fails in a way the router should fail over on."""


@runtime_checkable
class STTProvider(Protocol):
    name: str
    priority: int
    cost_per_minute_usd: float

    async def transcribe(self, audio: bytes) -> Transcript: ...


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    priority: int
    cost_per_1k_tokens_usd: float

    async def complete(self, prompt: str) -> Completion: ...
