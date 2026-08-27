"""Stream synthetic audio at a live server and print what comes back.

    uv run python scripts/demo_client.py [ws://host/ws/transcribe]

Sends 3 seconds of 16kHz PCM in realtime-ish pacing, then finalizes. Useful as a
30-second live demo of the whole path: chunking, routing, failover, note generation.
"""

from __future__ import annotations

import asyncio
import math
import struct
import sys

import websockets

SAMPLE_RATE = 16_000
CHUNK_MS = 320
SAMPLES_PER_CHUNK = SAMPLE_RATE * CHUNK_MS // 1000
SECONDS = 3


def tone_chunk(index: int) -> bytes:
    """A 320ms sine chunk. Not speech — the fakes key off bytes, not audio content."""
    freq = 220 + (index % 5) * 55
    samples = (
        int(12_000 * math.sin(2 * math.pi * freq * (i / SAMPLE_RATE)))
        for i in range(SAMPLES_PER_CHUNK)
    )
    return struct.pack(f"<{SAMPLES_PER_CHUNK}h", *samples)


async def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:8000/ws/transcribe"
    total_chunks = SECONDS * 1000 // CHUNK_MS

    print(f"connecting to {url}")
    async with websockets.connect(url) as ws:
        for i in range(total_chunks):
            await ws.send(tone_chunk(i))
            reply = await ws.recv()
            print(f"  <- {reply}")
            await asyncio.sleep(CHUNK_MS / 1000)

        print("finalizing")
        await ws.send("finalize")
        print(f"  <- {await ws.recv()}")


if __name__ == "__main__":
    asyncio.run(main())
