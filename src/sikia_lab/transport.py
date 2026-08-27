"""FastAPI surface: websocket audio ingest plus health.

The websocket protocol is intentionally boring — binary frames are audio, text
frames are control. Anything the client sends that we do not understand is ignored
rather than fatal, because a client bug should not end a consultation.
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from sikia_lab.pipeline import Session
from sikia_lab.providers.fake import FakeLLM, FakeSTT
from sikia_lab.router import Router

log = structlog.get_logger(__name__)


def build_stt_router() -> Router:
    return Router(
        [
            FakeSTT("deepgram", priority=0, latency_s=0.02, confidence=0.95),
            FakeSTT("assemblyai", priority=1, latency_s=0.05, confidence=0.93),
            FakeSTT("whisper-local", priority=2, latency_s=0.12, confidence=0.88),
        ]
    )


def build_llm_router() -> Router:
    return Router(
        [
            FakeLLM("claude", priority=0, latency_s=0.03),
            FakeLLM("gpt", priority=1, latency_s=0.04),
        ]
    )


app = FastAPI(title="sikia-lab", version="0.1.0")
app.state.stt_router = build_stt_router()
app.state.llm_router = build_llm_router()


@app.get("/healthz")
async def healthz() -> dict[str, object]:
    return {
        "status": "ok",
        "stt": app.state.stt_router.snapshot(),
        "llm": app.state.llm_router.snapshot(),
    }


@app.websocket("/ws/transcribe")
async def transcribe(ws: WebSocket) -> None:
    await ws.accept()
    session = Session(str(uuid.uuid4())[:8], app.state.stt_router, app.state.llm_router)
    log.info("session.opened", session=session.session_id)

    try:
        while True:
            message = await ws.receive()

            if message.get("type") == "websocket.disconnect":
                break

            if (audio := message.get("bytes")) is not None:
                for chunk in session.feed(audio):
                    segment = await session.transcribe_chunk(chunk)
                    if segment is None:
                        await ws.send_json({"type": "gap", "reason": "all_providers_failed"})
                    else:
                        await ws.send_json(
                            {
                                "type": "partial",
                                "text": segment.text,
                                "confidence": segment.confidence,
                                "provider": segment.provider,
                            }
                        )

            elif message.get("text") == "finalize":
                note = await session.finalize()
                await ws.send_json(
                    {
                        "type": "note",
                        "text": note,
                        "segments": len(session.segments),
                        "dropped_chunks": session.dropped_chunks,
                    }
                )
                break

    except WebSocketDisconnect:
        log.info("session.disconnected", session=session.session_id)
    finally:
        log.info(
            "session.closed",
            session=session.session_id,
            segments=len(session.segments),
            dropped=session.dropped_chunks,
        )
