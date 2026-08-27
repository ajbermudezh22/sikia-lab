"""Health-aware provider routing.

The design assumption is that providers fail independently and often, and that a
clinical session cannot pause while one of them recovers. So:

* every call gets a hard timeout — a slow provider is treated as a failed one
* consecutive failures trip a circuit breaker and take the provider out of rotation
* a tripped breaker lets exactly one probe through after a cooldown, so recovery is
  automatic but a dead provider is not hammered
* failover walks the remaining providers in priority order, and the caller only sees
  an error when every provider is exhausted

The router deliberately knows nothing about what it is routing. `Router` is generic
over the call, so STT and LLM share one implementation and one set of tests.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum

import structlog

from sikia_lab.config import settings
from sikia_lab.providers.base import ProviderError

log = structlog.get_logger(__name__)


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class AllProvidersFailed(RuntimeError):
    """Every provider in the pool failed or was unavailable for this call."""

    def __init__(self, attempts: dict[str, str]) -> None:
        self.attempts = attempts
        detail = ", ".join(f"{name}={reason}" for name, reason in attempts.items())
        super().__init__(f"all providers failed: {detail or 'pool empty'}")


@dataclass
class Health:
    """Rolling health for one provider."""

    consecutive_failures: int = 0
    total_calls: int = 0
    total_failures: int = 0
    opened_at: float | None = None
    ewma_latency_s: float = 0.0
    _probing: bool = field(default=False, repr=False)

    def state(self, now: float, cooldown_s: float) -> BreakerState:
        if self.opened_at is None:
            return BreakerState.CLOSED
        if now - self.opened_at >= cooldown_s:
            return BreakerState.HALF_OPEN
        return BreakerState.OPEN

    def record_success(self, latency_s: float) -> None:
        self.total_calls += 1
        self.consecutive_failures = 0
        self.opened_at = None
        self._probing = False
        # EWMA with alpha=0.3: recent calls dominate without a single spike owning it.
        self.ewma_latency_s = (
            latency_s if self.ewma_latency_s == 0.0 else 0.7 * self.ewma_latency_s + 0.3 * latency_s
        )

    def record_failure(self, now: float, threshold: int) -> None:
        self.total_calls += 1
        self.total_failures += 1
        self.consecutive_failures += 1
        self._probing = False
        if self.consecutive_failures >= threshold:
            self.opened_at = now

    @property
    def failure_rate(self) -> float:
        return self.total_failures / self.total_calls if self.total_calls else 0.0


class Router[P, T]:
    """Routes one logical call across a pool of interchangeable providers."""

    def __init__(
        self,
        providers: list[P],
        *,
        timeout_s: float | None = None,
        breaker_threshold: int | None = None,
        breaker_cooldown_s: float | None = None,
    ) -> None:
        if not providers:
            raise ValueError("Router needs at least one provider")
        self.providers = sorted(providers, key=lambda p: p.priority)  # type: ignore[attr-defined]
        self.timeout_s = timeout_s if timeout_s is not None else settings.call_timeout_s
        self.threshold = (
            breaker_threshold if breaker_threshold is not None else settings.breaker_threshold
        )
        self.cooldown_s = (
            breaker_cooldown_s if breaker_cooldown_s is not None else settings.breaker_cooldown_s
        )
        self.health: dict[str, Health] = {p.name: Health() for p in self.providers}  # type: ignore[attr-defined]

    def available(self, now: float | None = None) -> list[P]:
        """Providers that are currently allowed to take traffic, best first."""
        now = now if now is not None else time.monotonic()
        out: list[P] = []
        for p in self.providers:
            h = self.health[p.name]  # type: ignore[attr-defined]
            state = h.state(now, self.cooldown_s)
            if state is BreakerState.OPEN:
                continue
            if state is BreakerState.HALF_OPEN and h._probing:
                # Another task already holds this provider's single probe slot.
                continue
            out.append(p)
        return out

    async def call(self, fn: Callable[[P], Awaitable[T]]) -> T:
        """Run `fn` against the healthiest provider, failing over on error or timeout.

        Raises AllProvidersFailed only when every provider has been tried and failed.
        """
        attempts: dict[str, str] = {}

        for provider in self.available():
            name = provider.name  # type: ignore[attr-defined]
            h = self.health[name]
            now = time.monotonic()
            if h.state(now, self.cooldown_s) is BreakerState.HALF_OPEN:
                h._probing = True

            started = time.monotonic()
            try:
                result = await asyncio.wait_for(fn(provider), timeout=self.timeout_s)
            except TimeoutError:
                elapsed = time.monotonic() - started
                h.record_failure(time.monotonic(), self.threshold)
                attempts[name] = f"timeout after {elapsed:.2f}s"
                log.warning("provider.timeout", provider=name, elapsed_s=round(elapsed, 3))
                continue
            except ProviderError as exc:
                h.record_failure(time.monotonic(), self.threshold)
                attempts[name] = str(exc)
                log.warning("provider.error", provider=name, error=str(exc))
                continue
            except Exception as exc:  # unexpected adapter bug — fail over, but say so loudly
                h.record_failure(time.monotonic(), self.threshold)
                attempts[name] = f"unexpected {type(exc).__name__}: {exc}"
                log.error("provider.unexpected", provider=name, error=str(exc), exc_info=True)
                continue

            h.record_success(time.monotonic() - started)
            if attempts:
                log.info("provider.failover_recovered", served_by=name, failed=list(attempts))
            return result

        # Nothing available: every provider is either open or just failed in this loop.
        for p in self.providers:
            attempts.setdefault(p.name, "circuit open")  # type: ignore[attr-defined]
        raise AllProvidersFailed(attempts)

    def snapshot(self) -> dict[str, dict[str, object]]:
        """Health of the pool, for the /healthz endpoint and for tests."""
        now = time.monotonic()
        return {
            p.name: {  # type: ignore[attr-defined]
                "state": self.health[p.name].state(now, self.cooldown_s).value,  # type: ignore[attr-defined]
                "priority": p.priority,  # type: ignore[attr-defined]
                "consecutive_failures": self.health[p.name].consecutive_failures,  # type: ignore[attr-defined]
                "failure_rate": round(self.health[p.name].failure_rate, 3),  # type: ignore[attr-defined]
                "ewma_latency_ms": round(self.health[p.name].ewma_latency_s * 1000, 1),  # type: ignore[attr-defined]
            }
            for p in self.providers
        }
