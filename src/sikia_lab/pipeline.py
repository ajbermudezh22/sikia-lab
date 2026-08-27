"""Session pipeline: audio chunks in, transcript segments and a note out.

A `Session` owns the state for one consultation. It buffers incoming audio into
fixed-size chunks (the STT providers want consistent framing), routes each chunk
through the STT router, and accumulates the transcript. When the session closes it
runs one summarization pass to produce the clinical note.

Backpressure note: transcription runs inline per chunk. That is correct for the
current chunk size — a 320ms chunk against a ~200ms provider leaves headroom — but
it is the first thing that breaks under a slow provider, which is why the router's
timeout is deliberately tighter than the chunk duration budget allows for retries.
"""

from __future__ import annotations

import structlog

from sikia_lab.config import settings
from sikia_lab.providers.base import Transcript
from sikia_lab.router import AllProvidersFailed, Router

log = structlog.get_logger(__name__)

SUMMARY_PROMPT = """\
You are documenting a medical consultation. Produce a structured note with sections:
Subjective, Objective, Assessment, Plan. Use only information present in the
transcript. Where the transcript is unclear, write [unclear] rather than inferring.

Transcript:
{transcript}
"""


class Session:
    def __init__(
        self,
        session_id: str,
        stt_router: Router,
        llm_router: Router,
        *,
        chunk_bytes: int | None = None,
    ) -> None:
        self.session_id = session_id
        self.stt = stt_router
        self.llm = llm_router
        self.chunk_bytes = chunk_bytes or settings.bytes_per_chunk
        self._buffer = bytearray()
        self.segments: list[Transcript] = []
        self.dropped_chunks = 0

    def feed(self, audio: bytes) -> list[bytes]:
        """Buffer audio and return whatever complete chunks are now ready."""
        self._buffer.extend(audio)
        ready: list[bytes] = []
        while len(self._buffer) >= self.chunk_bytes:
            ready.append(bytes(self._buffer[: self.chunk_bytes]))
            del self._buffer[: self.chunk_bytes]
        return ready

    async def transcribe_chunk(self, chunk: bytes) -> Transcript | None:
        """Transcribe one chunk. Returns None if every provider failed.

        A dropped chunk is a hole in the transcript, not a dead session — we count it
        and keep going, because ending a live consultation is worse than a gap.
        """
        try:
            segment = await self.stt.call(lambda p: p.transcribe(chunk))
        except AllProvidersFailed as exc:
            self.dropped_chunks += 1
            log.error("stt.chunk_dropped", session=self.session_id, attempts=exc.attempts)
            return None
        self.segments.append(segment)
        return segment

    @property
    def transcript(self) -> str:
        return " ".join(s.text for s in self.segments)

    async def finalize(self) -> str:
        """Flush any partial audio, then summarize into a clinical note."""
        if self._buffer:
            await self.transcribe_chunk(bytes(self._buffer))
            self._buffer.clear()

        if not self.segments:
            return "[no audio captured]"

        prompt = SUMMARY_PROMPT.format(transcript=self.transcript)
        completion = await self.llm.call(lambda p: p.complete(prompt))
        log.info(
            "session.finalized",
            session=self.session_id,
            segments=len(self.segments),
            dropped=self.dropped_chunks,
            provider=completion.provider,
        )
        return completion.text
