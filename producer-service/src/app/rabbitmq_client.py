import json
import logging
import time
from threading import RLock
from typing import Any, Dict

import pika

from app.config import Settings


logger = logging.getLogger(__name__)


class RabbitMQPublisher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._connection: pika.BlockingConnection | None = None
        self._channel: pika.channel.Channel | None = None
        self._lock = RLock()

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

    def connect(self) -> None:
        with self._lock:
            if self._connection and self._connection.is_open and self._channel and self._channel.is_open:
                return

            last_error: Exception | None = None
            for attempt in range(1, self.settings.rabbitmq_connection_retries + 1):
                try:
                    connection = pika.BlockingConnection(self._build_parameters())
                    channel = connection.channel()
                    channel.queue_declare(queue=self.settings.rabbitmq_queue, durable=True)
                    self._connection = connection
                    self._channel = channel
                    logger.info("Producer connected to RabbitMQ")
                    return
                except Exception as error:  # pragma: no cover - exercised in integration
                    last_error = error
                    logger.warning(
                        "Producer failed to connect to RabbitMQ (attempt %s/%s): %s",
                        attempt,
                        self.settings.rabbitmq_connection_retries,
                        error,
                    )
                    time.sleep(self.settings.rabbitmq_retry_delay_seconds)

            raise RuntimeError("Producer could not connect to RabbitMQ") from last_error

    def close(self) -> None:
        with self._lock:
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

    def publish_event(self, event_payload: Dict[str, Any]) -> None:
        with self._lock:
            if not self._connection or not self._connection.is_open or not self._channel or not self._channel.is_open:
                self.connect()

            assert self._channel is not None

            message = json.dumps(event_payload)
            self._channel.basic_publish(
                exchange="",
                routing_key=self.settings.rabbitmq_queue,
                body=message,
                properties=pika.BasicProperties(delivery_mode=2),
            )
            logger.info("Published event for user_id=%s", event_payload.get("user_id"))

    def check_health(self) -> bool:
        try:
            self.connect()
            assert self._channel is not None
            self._channel.queue_declare(queue=self.settings.rabbitmq_queue, passive=True)
            return True
        except Exception as error:  # pragma: no cover - dependent on external service
            logger.error("RabbitMQ health check failed: %s", error)
            return False
