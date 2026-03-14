import json
import os
import time
import uuid

import mysql.connector
import pika
import pytest


pytestmark = pytest.mark.integration


def _integration_enabled() -> bool:
    return os.getenv("RUN_INTEGRATION_TESTS", "0") == "1"


@pytest.mark.skipif(not _integration_enabled(), reason="Set RUN_INTEGRATION_TESTS=1 to run integration tests")
def test_consumer_persists_event_published_to_queue() -> None:
    request_id = str(uuid.uuid4())
    queue_name = os.getenv("RABBITMQ_QUEUE", "user_activity_events")

    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=os.getenv("RABBITMQ_HOST", "rabbitmq"),
            port=int(os.getenv("RABBITMQ_PORT", "5672")),
            virtual_host=os.getenv("RABBITMQ_VIRTUAL_HOST", "/"),
            credentials=pika.PlainCredentials(
                username=os.getenv("RABBITMQ_USER", "guest"),
                password=os.getenv("RABBITMQ_PASSWORD", "guest"),
            ),
        )
    )
    channel = connection.channel()
    channel.queue_declare(queue=queue_name, durable=True)

    payload = {
        "user_id": 111,
        "event_type": "login",
        "timestamp": "2026-03-13T10:00:00Z",
        "metadata": {
            "request_id": request_id,
            "source": "consumer-integration-test",
        },
    }

    channel.basic_publish(
        exchange="",
        routing_key=queue_name,
        body=json.dumps(payload),
        properties=pika.BasicProperties(delivery_mode=2),
    )
    connection.close()

    conn = mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "mysql"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", "root_password"),
        database=os.getenv("MYSQL_DB", "user_activity_db"),
        autocommit=True,
    )

    try:
        found = False
        deadline = time.time() + 20
        while time.time() < deadline:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id
                FROM user_activities
                WHERE user_id = %s
                AND event_type = %s
                AND JSON_UNQUOTE(JSON_EXTRACT(metadata, '$.request_id')) = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (payload["user_id"], payload["event_type"], request_id),
            )
            row = cursor.fetchone()
            cursor.close()

            if row:
                found = True
                break

            time.sleep(1)

        assert found is True
    finally:
        conn.close()
