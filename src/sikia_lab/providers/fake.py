"""Deterministic fakes.

These are not throwaway mocks — they are the substrate the router tests run against,
so they model the failure modes we actually care about: slowness, hard errors, and
degraded-but-successful responses. `fail_after`/`recover_after` let a test drive a
provider through an outage and out the other side.
"""

from __future__ import annotations

import asyncio
import hashlib

from sikia_lab.providers.base import Completion, ProviderError, Transcript


class FakeSTT:
    def __init__(
        self,
        name: str,
        priority: int = 0,
        latency_s: float = 0.01,
        confidence: float = 0.95,
        cost_per_minute_usd: float = 0.006,
        fail_after: int | None = None,
        recover_after: int | None = None,
    ) -> None:
        self.name = name
        self.priority = priority
        self.latency_s = latency_s
        self.confidence = confidence
        self.cost_per_minute_usd = cost_per_minute_usd
        self.fail_after = fail_after
        self.recover_after = recover_after
        self.calls = 0

    def _should_fail(self) -> bool:
        if self.fail_after is None or self.calls <= self.fail_after:
            return False
        if self.recover_after is not None and self.calls > self.recover_after:
            return False
        return True

    async def transcribe(self, audio: bytes) -> Transcript:
        self.calls += 1
        await asyncio.sleep(self.latency_s)
        if self._should_fail():
            raise ProviderError(f"{self.name}: simulated upstream failure")
        digest = hashlib.sha256(audio).hexdigest()[:8]
        return Transcript(
            text=f"[{self.name}] chunk-{digest}",
            confidence=self.confidence,
            provider=self.name,
        )


class FakeLLM:
    def __init__(
        self,
        name: str,
        priority: int = 0,
        latency_s: float = 0.01,
        cost_per_1k_tokens_usd: float = 0.003,
        fail_after: int | None = None,
        recover_after: int | None = None,
    ) -> None:
        self.name = name
        self.priority = priority
        self.latency_s = latency_s
        self.cost_per_1k_tokens_usd = cost_per_1k_tokens_usd
        self.fail_after = fail_after
        self.recover_after = recover_after
        self.calls = 0

    async def complete(self, prompt: str) -> Completion:
        self.calls += 1
        await asyncio.sleep(self.latency_s)
        if self.fail_after is not None and self.calls > self.fail_after:
            if self.recover_after is None or self.calls <= self.recover_after:
                raise ProviderError(f"{self.name}: simulated upstream failure")
        return Completion(
            text=f"[{self.name}] {prompt[:64]}",
            provider=self.name,
            input_tokens=len(prompt) // 4,
            output_tokens=32,
        )
