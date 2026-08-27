from __future__ import annotations

from fastapi.testclient import TestClient

from sikia_lab.transport import app

client = TestClient(app)


def test_healthz_reports_every_provider():
    body = client.get("/healthz").json()

    assert body["status"] == "ok"
    assert set(body["stt"]) == {"deepgram", "assemblyai", "whisper-local"}
    assert all(p["state"] == "closed" for p in body["stt"].values())


def test_websocket_streams_partials_then_a_final_note():
    chunk = b"\x00\x01" * 5120  # one full 320ms chunk at 16kHz 16-bit

    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_bytes(chunk)
        partial = ws.receive_json()

        assert partial["type"] == "partial"
        assert partial["provider"] == "deepgram"

        ws.send_text("finalize")
        note = ws.receive_json()

    assert note["type"] == "note"
    assert note["segments"] >= 1
    assert note["dropped_chunks"] == 0


def test_partial_audio_is_buffered_and_not_transcribed_early():
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_bytes(b"\x00" * 64)  # far below one chunk
        ws.send_text("finalize")
        note = ws.receive_json()

    assert note["type"] == "note"
    assert note["segments"] == 1, "the buffered remainder is flushed exactly once"


def test_unknown_control_message_does_not_kill_the_session():
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_text("garbage")
        ws.send_bytes(b"\x00\x01" * 5120)
        partial = ws.receive_json()

    assert partial["type"] == "partial"
