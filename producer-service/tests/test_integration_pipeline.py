import os
import time
import uuid

import httpx
import mysql.connector
import pytest


pytestmark = pytest.mark.integration


def _integration_enabled() -> bool:
    return os.getenv("RUN_INTEGRATION_TESTS", "0") == "1"


@pytest.mark.skipif(not _integration_enabled(), reason="Set RUN_INTEGRATION_TESTS=1 to run integration tests")
def test_event_is_persisted_after_api_publish() -> None:
    request_id = str(uuid.uuid4())
    payload = {
        "user_id": 4242,
        "event_type": "page_view",
        "timestamp": "2026-03-13T10:00:00Z",
        "metadata": {
            "request_id": request_id,
            "page_url": "/products/item-xyz",
            "session_id": "abc123",
        },
    }

    response = httpx.post("http://127.0.0.1:8000/api/v1/events/track", json=payload, timeout=10.0)
    assert response.status_code == 202

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
