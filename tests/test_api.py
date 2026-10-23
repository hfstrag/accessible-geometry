import json
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from accessible_geometry.api.routes import get_service
from accessible_geometry.config import Settings
from accessible_geometry.conversation import MAX_EXCHANGES, Exchange
from accessible_geometry.geometry.actions import CreatePoint, CreateSegment
from accessible_geometry.main import create_app
from accessible_geometry.service import VoiceCommandService
from tests.fakes import FakeInterpreter, FakeTranscriber


@pytest.fixture
def app() -> FastAPI:
    return create_app(Settings(groq_api_key=None, max_audio_bytes=1000, _env_file=None))  # type: ignore[call-arg]


@pytest.fixture
def transcriber() -> FakeTranscriber:
    return FakeTranscriber("place le point A en 1 2")


@pytest.fixture
def interpreter() -> FakeInterpreter:
    return FakeInterpreter([CreatePoint(name="A", x=1, y=2)])


@pytest.fixture
def client(
    app: FastAPI, transcriber: FakeTranscriber, interpreter: FakeInterpreter
) -> Iterator[TestClient]:
    service = VoiceCommandService(transcriber, interpreter)
    app.dependency_overrides[get_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client


def test_health_reports_missing_key(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.json() == {"status": "ok", "ai_configured": False}


def test_commands_unavailable_without_key(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.post("/api/command", json={"text": "point A", "language": "fr"})
    assert response.status_code == 503


def test_serves_front_end(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "GeoGebra" in response.text or "ggb-container" in response.text


def test_text_command(client: TestClient) -> None:
    response = client.post("/api/command", json={"text": "place A en 1 2", "language": "fr"})
    assert response.status_code == 200
    assert response.json() == {
        "status": "executed",
        "transcript": "place A en 1 2",
        "message": "Point A placé en (1 ; 2).",
        "steps": [{"op": "eval", "command": "A = (1, 2)"}],
    }


def test_voice_command(client: TestClient, transcriber: FakeTranscriber) -> None:
    response = client.post(
        "/api/voice",
        files={"audio": ("speech.webm", b"fake-audio", "audio/webm")},
        data={"language": "en", "state": json.dumps({"objects": []})},
    )
    assert response.status_code == 200
    assert response.json()["transcript"] == "place le point A en 1 2"
    assert transcriber.calls == [(b"fake-audio", "speech.webm", "en")]


def test_voice_command_rejects_large_audio(client: TestClient) -> None:
    response = client.post(
        "/api/voice",
        files={"audio": ("speech.webm", b"x" * 1001, "audio/webm")},
        data={"language": "fr"},
    )
    assert response.status_code == 413


def test_voice_command_rejects_invalid_state(client: TestClient) -> None:
    response = client.post(
        "/api/voice",
        files={"audio": ("speech.webm", b"x", "audio/webm")},
        data={"language": "fr", "state": "not json"},
    )
    assert response.status_code == 422


def test_empty_transcript(client: TestClient, transcriber: FakeTranscriber) -> None:
    transcriber.transcript = "  "
    response = client.post(
        "/api/voice", files={"audio": ("a.webm", b"x", "audio/webm")}, data={"language": "en"}
    )
    assert response.json()["status"] == "empty"


def test_interpretation_failure(client: TestClient, interpreter: FakeInterpreter) -> None:
    interpreter.actions = None
    response = client.post("/api/command", json={"text": "blabla", "language": "en"})
    body = response.json()
    assert body["status"] == "rejected"
    assert body["message"] == "I didn't understand. Could you rephrase?"


def test_planning_failure_is_reported(client: TestClient, interpreter: FakeInterpreter) -> None:
    interpreter.actions = [CreateSegment(start="A", end="B")]
    response = client.post("/api/command", json={"text": "segment AB", "language": "fr"})
    body = response.json()
    assert body["status"] == "rejected"
    assert body["steps"] == []
    assert body["message"] == "Je ne trouve pas A dans la figure."


def test_history_is_passed_to_interpreter(client: TestClient, interpreter: FakeInterpreter) -> None:
    history = [{"user": "place A", "assistant": "Point A placé."}]
    client.post(
        "/api/voice",
        files={"audio": ("a.webm", b"x", "audio/webm")},
        data={"language": "fr", "history": json.dumps(history)},
    )
    client.post("/api/command", json={"text": "B", "language": "fr", "history": history})

    assert [h for _, h in interpreter.calls] == [[Exchange(**history[0])]] * 2


def test_history_length_is_limited(client: TestClient) -> None:
    history = [{"user": "a", "assistant": "b"}] * (MAX_EXCHANGES + 1)
    response = client.post("/api/command", json={"text": "B", "language": "fr", "history": history})
    assert response.status_code == 422
