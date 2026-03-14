from typing import Any

from fastapi.testclient import TestClient

from app.main import app, get_publisher


class FakePublisher:
    def __init__(self, should_fail: bool = False, healthy: bool = True) -> None:
        self.should_fail = should_fail
        self.healthy = healthy
        self.published_events: list[dict[str, Any]] = []

    def publish_event(self, event_payload: dict[str, Any]) -> None:
        if self.should_fail:
            raise RuntimeError("publish failed")
        self.published_events.append(event_payload)

    def check_health(self) -> bool:
        return self.healthy



def test_track_event_returns_202_and_publishes_message() -> None:
    fake_publisher = FakePublisher()
    app.dependency_overrides[get_publisher] = lambda: fake_publisher

    client = TestClient(app)
    response = client.post(
        "/api/v1/events/track",
        json={
            "user_id": 123,
            "event_type": "page_view",
            "timestamp": "2026-03-13T10:00:00Z",
            "metadata": {"page_url": "/pricing", "session_id": "abc123"},
        },
    )

    assert response.status_code == 202
    assert response.json()["message"] == "Event accepted and queued"
    assert len(fake_publisher.published_events) == 1

    app.dependency_overrides.clear()



def test_track_event_returns_400_for_invalid_payload() -> None:
    fake_publisher = FakePublisher()
    app.dependency_overrides[get_publisher] = lambda: fake_publisher

    client = TestClient(app)
    response = client.post(
        "/api/v1/events/track",
        json={
            "event_type": "page_view",
            "timestamp": "2026-03-13T10:00:00Z",
            "metadata": {"page_url": "/pricing"},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid request payload"

    app.dependency_overrides.clear()



def test_track_event_returns_503_when_publish_fails() -> None:
    fake_publisher = FakePublisher(should_fail=True)
    app.dependency_overrides[get_publisher] = lambda: fake_publisher

    client = TestClient(app)
    response = client.post(
        "/api/v1/events/track",
        json={
            "user_id": 1,
            "event_type": "login",
            "timestamp": "2026-03-13T10:00:00Z",
            "metadata": {"ip": "127.0.0.1"},
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Unable to enqueue event"

    app.dependency_overrides.clear()



def test_health_returns_200_when_dependency_is_healthy() -> None:
    fake_publisher = FakePublisher(healthy=True)
    app.dependency_overrides[get_publisher] = lambda: fake_publisher

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    app.dependency_overrides.clear()
