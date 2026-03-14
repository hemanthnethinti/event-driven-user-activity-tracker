from typing import Any

from app.config import Settings
from app.worker import EventProcessor


class FakeRepository:
    def __init__(self, fail_times: int = 0) -> None:
        self.fail_times = fail_times
        self.calls = 0
        self.inserted_events: list[Any] = []

    def connect(self) -> None:
        return

    def ping(self) -> bool:
        return True

    def insert_activity(self, event: Any) -> None:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("temporary db error")
        self.inserted_events.append(event)

    def close(self) -> None:
        return



def _settings() -> Settings:
    return Settings(
        db_insert_retries=3,
        db_insert_retry_delay_seconds=0,
    )



def test_process_payload_persists_valid_event() -> None:
    repository = FakeRepository()
    processor = EventProcessor(repository, _settings())

    payload = (
        b'{"user_id": 5, "event_type": "login", '
        b'"timestamp": "2026-03-13T10:00:00Z", "metadata": {"ip": "127.0.0.1"}}'
    )

    result = processor.process_payload(payload)

    assert result is True
    assert len(repository.inserted_events) == 1



def test_process_payload_rejects_malformed_message() -> None:
    repository = FakeRepository()
    processor = EventProcessor(repository, _settings())

    result = processor.process_payload(b"{invalid-json")

    assert result is False
    assert len(repository.inserted_events) == 0



def test_process_payload_retries_then_succeeds() -> None:
    repository = FakeRepository(fail_times=2)
    processor = EventProcessor(repository, _settings())

    payload = (
        b'{"user_id": 9, "event_type": "logout", '
        b'"timestamp": "2026-03-13T10:00:00Z", "metadata": {"session_id": "abc"}}'
    )

    result = processor.process_payload(payload)

    assert result is True
    assert repository.calls == 3
    assert len(repository.inserted_events) == 1



def test_process_payload_drops_after_retry_exhaustion() -> None:
    repository = FakeRepository(fail_times=10)
    processor = EventProcessor(repository, _settings())

    payload = (
        b'{"user_id": 3, "event_type": "page_view", '
        b'"timestamp": "2026-03-13T10:00:00Z", "metadata": {"page_url": "/home"}}'
    )

    result = processor.process_payload(payload)

    assert result is False
    assert repository.calls == 3
    assert len(repository.inserted_events) == 0
