from __future__ import annotations

from sikia_lab.pipeline import Session
from sikia_lab.providers.fake import FakeLLM, FakeSTT
from sikia_lab.router import Router


def build(**stt_kwargs) -> Session:
    stt = Router([FakeSTT("stt", priority=0, **stt_kwargs)])
    llm = Router([FakeLLM("llm", priority=0)])
    return Session("test", stt, llm, chunk_bytes=100)


def test_feed_emits_only_complete_chunks():
    session = build()

    assert session.feed(b"x" * 40) == []
    assert session.feed(b"x" * 40) == []
    chunks = session.feed(b"x" * 40)

    assert len(chunks) == 1
    assert len(chunks[0]) == 100


def test_feed_emits_multiple_chunks_from_one_burst():
    session = build()
    chunks = session.feed(b"x" * 250)

    assert [len(c) for c in chunks] == [100, 100]


async def test_dropped_chunk_leaves_a_gap_but_keeps_the_session_alive():
    session = build(fail_after=0)

    result = await session.transcribe_chunk(b"x" * 100)

    assert result is None
    assert session.dropped_chunks == 1
    assert session.segments == []


async def test_finalize_flushes_partial_audio_and_summarizes():
    session = build()
    session.feed(b"x" * 150)  # 100 consumed as a chunk, 50 left buffered
    await session.transcribe_chunk(b"x" * 100)

    note = await session.finalize()

    assert len(session.segments) == 2, "the trailing partial buffer must be transcribed"
    assert "llm" in note


async def test_finalize_with_no_audio_does_not_call_the_llm():
    session = build()

    note = await session.finalize()

    assert note == "[no audio captured]"
