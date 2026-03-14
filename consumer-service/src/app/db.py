import json
import logging
import time
from datetime import timezone
from threading import Lock

import mysql.connector
from mysql.connector import Error

from app.config import Settings
from app.schemas import UserActivityEvent


logger = logging.getLogger(__name__)


class MySQLActivityRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._connection: mysql.connector.MySQLConnection | None = None
        self._lock = Lock()

    def connect(self) -> None:
        with self._lock:
            if self._connection and self._connection.is_connected():
                return

            last_error: Exception | None = None
            for attempt in range(1, self.settings.mysql_connection_retries + 1):
                try:
                    self._connection = mysql.connector.connect(
                        host=self.settings.mysql_host,
                        port=self.settings.mysql_port,
                        user=self.settings.mysql_user,
                        password=self.settings.mysql_password,
                        database=self.settings.mysql_db,
                    )
                    logger.info("Consumer connected to MySQL")
                    return
                except Error as error:
                    last_error = error
                    logger.warning(
                        "Consumer failed to connect to MySQL (attempt %s/%s): %s",
                        attempt,
                        self.settings.mysql_connection_retries,
                        error,
                    )
                    time.sleep(self.settings.mysql_retry_delay_seconds)

            raise RuntimeError("Consumer could not connect to MySQL") from last_error

    def ping(self) -> bool:
        try:
            self.connect()
            assert self._connection is not None
            cursor = self._connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception as error:  # pragma: no cover - depends on external service
            logger.error("MySQL ping failed: %s", error)
            return False

    def insert_activity(self, event: UserActivityEvent) -> None:
        self.connect()
        assert self._connection is not None

        timestamp_utc = event.timestamp.astimezone(timezone.utc).replace(tzinfo=None)

        cursor = self._connection.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO user_activities (user_id, event_type, timestamp, metadata)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    event.user_id,
                    event.event_type,
                    timestamp_utc,
                    json.dumps(event.metadata),
                ),
            )
            self._connection.commit()
        finally:
            cursor.close()

    def close(self) -> None:
        with self._lock:
            if self._connection and self._connection.is_connected():
                self._connection.close()
            self._connection = None
