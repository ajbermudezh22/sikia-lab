"""Latency and cost numbers for the routing layer.

Run: uv run python scripts/bench.py

Measures the router's own overhead and what failover actually costs, because
"we fail over automatically" is only a good story if you know the p99 it buys.
"""

from __future__ import annotations

import asyncio
import logging
import statistics
import time

import structlog

from sikia_lab.providers.fake import FakeSTT
from sikia_lab.router import Router

# Failover is loud by design; the numbers are the point here, so mute the logs.
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL))

AUDIO = b"\x00\x01" * 5120  # one 320ms chunk at 16kHz 16-bit
ITERATIONS = 300


async def measure(label: str, router: Router, iterations: int = ITERATIONS) -> None:
    samples: list[float] = []
    failures = 0

    for _ in range(iterations):
        started = time.perf_counter()
        try:
            await router.call(lambda p: p.transcribe(AUDIO))
        except Exception:
            failures += 1
        samples.append((time.perf_counter() - started) * 1000)

    samples.sort()
    p50 = statistics.median(samples)
    p95 = samples[int(len(samples) * 0.95)]
    p99 = samples[int(len(samples) * 0.99)]
    print(f"{label:<34} p50={p50:6.2f}ms  p95={p95:6.2f}ms  p99={p99:6.2f}ms  failures={failures}")


async def main() -> None:
    print(f"\n{ITERATIONS} calls per scenario, one 320ms audio chunk each\n")

    await measure(
        "healthy primary",
        Router([FakeSTT("primary", priority=0, latency_s=0.002)]),
    )

    await measure(
        "primary down, failover to backup",
        Router(
            [
                FakeSTT("primary", priority=0, latency_s=0.002, fail_after=0),
                FakeSTT("backup", priority=1, latency_s=0.002),
            ],
            breaker_threshold=1_000_000,  # never trip: measures the per-call failover cost
        ),
    )

    await measure(
        "primary down, breaker open after 3",
        Router(
            [
                FakeSTT("primary", priority=0, latency_s=0.002, fail_after=0),
                FakeSTT("backup", priority=1, latency_s=0.002),
            ],
            breaker_threshold=3,
            breaker_cooldown_s=3600,
        ),
    )

    await measure(
        "primary hangs, 50ms timeout",
        Router(
            [
                FakeSTT("hung", priority=0, latency_s=10.0),
                FakeSTT("backup", priority=1, latency_s=0.002),
            ],
            timeout_s=0.05,
            breaker_threshold=1_000_000,
        ),
        iterations=40,
    )

    print(
        "\nThe point: an open breaker turns a permanently-failing primary from a "
        "per-call tax into a one-time cost.\n"
        "A hung provider is the expensive case — the timeout is a floor on p99, which "
        "is why it is set below the chunk duration.\n"
    )


if __name__ == "__main__":
    asyncio.run(main())
