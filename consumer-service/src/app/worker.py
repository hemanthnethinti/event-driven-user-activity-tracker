import json
import logging
import threading
import time
from typing import Protocol

import pika
from pydantic import ValidationError

from app.config import Settings
from app.schemas import UserActivityEvent


logger = logging.getLogger(__name__)


class ActivityRepository(Protocol):
    def connect(self) -> None: ...

    def ping(self) -> bool: ...

    def insert_activity(self, event: UserActivityEvent) -> None: ...

    def close(self) -> None: ...


class EventProcessor:
    def __init__(self, repository: ActivityRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    def process_payload(self, payload: bytes) -> bool:
        try:
            data = json.loads(payload.decode("utf-8"))
            event = UserActivityEvent.model_validate(data)
        except (json.JSONDecodeError, UnicodeDecodeError, ValidationError) as error:
            logger.error("Dropping malformed message: %s", error)
            return False

        for attempt in range(1, self.settings.db_insert_retries + 1):
            try:
                self.repository.insert_activity(event)
                logger.info(
                    "Persisted event user_id=%s event_type=%s",
                    event.user_id,
                    event.event_type,
                )
                return True
            except Exception as error:  # pragma: no cover - retries tested via fakes
                logger.error(
                    "Failed to persist event (attempt %s/%s): %s",
                    attempt,
                    self.settings.db_insert_retries,
                    error,
                )
                if attempt < self.settings.db_insert_retries:
                    time.sleep(self.settings.db_insert_retry_delay_seconds)

        logger.error("Dropping message after persistence retries exhausted")
        return False


class ConsumerWorker:
    def __init__(
        self,
        settings: Settings,
        repository: ActivityRepository,
        processor: EventProcessor,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.processor = processor

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._connection: pika.BlockingConnection | None = None
        self._channel: pika.channel.Channel | None = None

        self._running = False
        self._rabbitmq_connected = False
        self._mysql_connected = False
        self._status_lock = threading.Lock()

    def _build_parameters(self) -> pika.ConnectionParameters:
        credentials = pika.PlainCredentials(
            username=self.settings.rabbitmq_user,
            password=self.settings.rabbitmq_password,
        )
        return pika.ConnectionParameters(
            host=self.settings.rabbitmq_host,
            port=self.settings.rabbitmq_port,
            virtual_host=self.settings.rabbitmq_virtual_host,
            credentials=credentials,
            heartbeat=self.settings.rabbitmq_heartbeat,
            blocked_connection_timeout=self.settings.rabbitmq_blocked_connection_timeout,
        )

    def _set_status(self, *, running: bool | None = None, rabbitmq: bool | None = None, mysql: bool | None = None) -> None:
        with self._status_lock:
            if running is not None:
                self._running = running
            if rabbitmq is not None:
                self._rabbitmq_connected = rabbitmq
            if mysql is not None:
                self._mysql_connected = mysql

    def health_status(self) -> dict[str, object]:
        with self._status_lock:
            healthy = self._running and self._rabbitmq_connected and self._mysql_connected
            return {
                "service": self.settings.app_name,
                "status": "ok" if healthy else "degraded",
                "healthy": healthy,
                "rabbitmq_connected": self._rabbitmq_connected,
                "mysql_connected": self._mysql_connected,
            }

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._close_rabbitmq()
        self.repository.close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        self._set_status(running=False, rabbitmq=False, mysql=False)

    def _close_rabbitmq(self) -> None:
        try:
            if self._channel and self._channel.is_open:
                self._channel.close()
        finally:
            self._channel = None

        try:
            if self._connection and self._connection.is_open:
                self._connection.close()
        finally:
            self._connection = None

    def _connect_dependencies(self) -> None:
        self.repository.connect()
        self._set_status(mysql=True)

        self._connection = pika.BlockingConnection(self._build_parameters())
        self._channel = self._connection.channel()
        self._channel.queue_declare(queue=self.settings.rabbitmq_queue, durable=True)
        self._channel.basic_qos(prefetch_count=20)
        self._set_status(rabbitmq=True)

    def _run_loop(self) -> None:
        self._set_status(running=True)
        logger.info("Consumer worker started")

        while not self._stop_event.is_set():
            try:
                self._connect_dependencies()
                assert self._channel is not None

                for method_frame, _properties, body in self._channel.consume(
                    queue=self.settings.rabbitmq_queue,
                    inactivity_timeout=1,
                    auto_ack=False,
                ):
                    if self._stop_event.is_set():
                        break

                    if method_frame is None:
                        continue

                    try:
                        self.processor.process_payload(body)
                    finally:
                        self._channel.basic_ack(delivery_tag=method_frame.delivery_tag)

                if self._channel and self._channel.is_open:
                    self._channel.cancel()
            except Exception as error:
                logger.error("Consumer loop error: %s", error)
                self._set_status(rabbitmq=False, mysql=self.repository.ping())
                time.sleep(self.settings.rabbitmq_retry_delay_seconds)
            finally:
                self._close_rabbitmq()

        self.repository.close()
        self._set_status(running=False, rabbitmq=False, mysql=False)
        logger.info("Consumer worker stopped")
