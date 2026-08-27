"""Router tests.

These are the tests that matter: the router's whole job is behaving correctly when
providers misbehave, so every test here is a failure scenario.
"""

from __future__ import annotations

import asyncio

import pytest

from sikia_lab.providers.fake import FakeSTT
from sikia_lab.router import AllProvidersFailed, BreakerState, Router

AUDIO = b"\x00\x01" * 512


def stt_router(*providers, **kwargs) -> Router:
    return Router(list(providers), **kwargs)


async def test_serves_from_highest_priority_when_healthy():
    primary = FakeSTT("primary", priority=0)
    backup = FakeSTT("backup", priority=1)
    router = stt_router(primary, backup)

    result = await router.call(lambda p: p.transcribe(AUDIO))

    assert result.provider == "primary"
    assert backup.calls == 0


async def test_fails_over_to_backup_when_primary_errors():
    primary = FakeSTT("primary", priority=0, fail_after=0)  # fails from the first call
    backup = FakeSTT("backup", priority=1)
    router = stt_router(primary, backup)

    result = await router.call(lambda p: p.transcribe(AUDIO))

    assert result.provider == "backup"
    assert primary.calls == 1


async def test_slow_provider_is_treated_as_failed():
    slow = FakeSTT("slow", priority=0, latency_s=5.0)
    fast = FakeSTT("fast", priority=1)
    router = stt_router(slow, fast, timeout_s=0.05)

    result = await router.call(lambda p: p.transcribe(AUDIO))

    assert result.provider == "fast"
    assert router.health["slow"].consecutive_failures == 1


async def test_breaker_opens_after_threshold_and_removes_provider():
    primary = FakeSTT("primary", priority=0, fail_after=0)
    backup = FakeSTT("backup", priority=1)
    router = stt_router(primary, backup, breaker_threshold=3, breaker_cooldown_s=60)

    for _ in range(3):
        await router.call(lambda p: p.transcribe(AUDIO))

    assert router.snapshot()["primary"]["state"] == BreakerState.OPEN.value
    assert [p.name for p in router.available()] == ["backup"]

    calls_before = primary.calls
    await router.call(lambda p: p.transcribe(AUDIO))
    assert primary.calls == calls_before, "open breaker must not send traffic"


async def test_breaker_half_opens_after_cooldown_and_recovers():
    # Fails calls 1-3, healthy again from call 4.
    primary = FakeSTT("primary", priority=0, fail_after=0, recover_after=3)
    backup = FakeSTT("backup", priority=1)
    router = stt_router(primary, backup, breaker_threshold=3, breaker_cooldown_s=0.05)

    for _ in range(3):
        await router.call(lambda p: p.transcribe(AUDIO))
    assert router.snapshot()["primary"]["state"] == BreakerState.OPEN.value

    await asyncio.sleep(0.06)
    assert router.snapshot()["primary"]["state"] == BreakerState.HALF_OPEN.value

    result = await router.call(lambda p: p.transcribe(AUDIO))

    assert result.provider == "primary", "probe should go to the recovering provider"
    assert router.snapshot()["primary"]["state"] == BreakerState.CLOSED.value


async def test_raises_when_every_provider_fails():
    a = FakeSTT("a", priority=0, fail_after=0)
    b = FakeSTT("b", priority=1, fail_after=0)
    router = stt_router(a, b)

    with pytest.raises(AllProvidersFailed) as exc:
        await router.call(lambda p: p.transcribe(AUDIO))

    assert set(exc.value.attempts) == {"a", "b"}


async def test_unexpected_adapter_exception_still_fails_over():
    class Broken:
        name = "broken"
        priority = 0
        cost_per_minute_usd = 0.0

        async def transcribe(self, audio: bytes):
            raise KeyError("adapter bug")

    router = stt_router(Broken(), FakeSTT("backup", priority=1))

    result = await router.call(lambda p: p.transcribe(AUDIO))

    assert result.provider == "backup"


async def test_health_snapshot_tracks_latency_and_failure_rate():
    primary = FakeSTT("primary", priority=0, latency_s=0.01)
    router = stt_router(primary)

    await router.call(lambda p: p.transcribe(AUDIO))
    snap = router.snapshot()["primary"]

    assert snap["state"] == "closed"
    assert snap["failure_rate"] == 0.0
    assert snap["ewma_latency_ms"] > 0


async def test_empty_pool_is_rejected_at_construction():
    with pytest.raises(ValueError):
        Router([])


async def test_concurrent_calls_share_one_probe_slot():
    """A half-open breaker must not let a burst of traffic hit a recovering provider."""
    primary = FakeSTT("primary", priority=0, latency_s=0.05, fail_after=0, recover_after=2)
    backup = FakeSTT("backup", priority=1)
    router = stt_router(primary, backup, breaker_threshold=2, breaker_cooldown_s=0.05)

    for _ in range(2):
        await router.call(lambda p: p.transcribe(AUDIO))
    await asyncio.sleep(0.06)

    calls_at_probe = primary.calls
    await asyncio.gather(*(router.call(lambda p: p.transcribe(AUDIO)) for _ in range(5)))

    assert primary.calls == calls_at_probe + 1, "only one probe should reach the provider"
