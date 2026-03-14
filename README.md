# Event-Driven User Activity Tracker

## Overview

This project implements a decoupled backend pipeline for tracking user activity events such as login, logout, and page view.

The system has two custom services:

- Producer API service: receives and validates activity events, then publishes them to RabbitMQ.
- Consumer worker service: consumes events asynchronously and persists them into MySQL.

Why this design:

- Producer latency stays low because API requests are not blocked by database work.
- Producer and consumer can scale independently.
- Temporary consumer failures do not require producer downtime.

## Architecture Summary

High-level flow:

Client -> Producer API -> RabbitMQ queue -> Consumer Worker -> MySQL

Primary queue:

- user_activity_events

## Key Features

- FastAPI endpoint for event ingestion: POST /api/v1/events/track
- Pydantic validation with clear 400 responses for invalid payloads
- Durable RabbitMQ queue and persistent messages
- Consumer-side retry loop for transient database failures
- Graceful shutdown for both services
- Dependency-aware health checks for producer and consumer
- Docker Compose orchestration for full local stack

## Tech Stack

- Language: Python 3.12
- API framework: FastAPI
- HTTP server: Uvicorn
- Message broker: RabbitMQ
- Database: MySQL 8
- Messaging client: Pika
- DB client: mysql-connector-python
- Validation/settings: Pydantic, pydantic-settings
- Testing: Pytest
- Runtime/deployment: Docker, Docker Compose

## Project Structure

```text
.
├── producer-service/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── src/app/
│   │   ├── config.py
│   │   ├── main.py
│   │   ├── models.py
│   │   └── rabbitmq_client.py
│   └── tests/
│       ├── test_api.py
│       └── test_integration_pipeline.py
├── consumer-service/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── src/app/
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── main.py
│   │   ├── schemas.py
│   │   └── worker.py
│   └── tests/
│       ├── test_worker.py
│       └── test_integration_consumer.py
├── db/
│   └── init.sql
├── tests/
│   └── README.md
├── docker-compose.yml
├── .env.example
├── ARCHITECTURE.md
├── DEV_NOTES.md
└── README.md
```

## API

### Track Event

- Method: POST
- Path: /api/v1/events/track
- Success: 202 Accepted
- Validation failure: 400 Bad Request
- Broker unavailable: 503 Service Unavailable

Request body:

```json
{
  "user_id": 123,
  "event_type": "page_view",
  "timestamp": "2026-03-13T10:00:00Z",
  "metadata": {
    "page_url": "/products/item-xyz",
    "session_id": "abc123"
  }
}
```

Success response:

```json
{
  "message": "Event accepted and queued"
}
```

### Health Endpoints

- Producer: GET /health on port 8000
- Consumer: GET /health on port 8001

Both return 200 when healthy and 503 when required dependencies are unavailable.

## Database Schema

MySQL initialization is handled automatically from db/init.sql.

```sql
CREATE TABLE IF NOT EXISTS user_activities (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    timestamp DATETIME NOT NULL,
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Quick Start

Prerequisite:

- Docker Desktop (or Docker Engine + Compose plugin)

Steps:

1. Create environment file:

```bash
cp .env.example .env
```

2. Build and start all services:

```bash
docker compose up --build -d
```

3. Verify health:

```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
```

4. Stop stack:

```bash
docker compose down -v
```

RabbitMQ management UI:

- URL: http://localhost:15672
- Username: guest
- Password: guest

## Environment Variables

Documented in .env.example.

RabbitMQ:

- RABBITMQ_HOST
- RABBITMQ_PORT
- RABBITMQ_USER
- RABBITMQ_PASSWORD
- RABBITMQ_VIRTUAL_HOST
- RABBITMQ_QUEUE

MySQL:

- MYSQL_HOST
- MYSQL_PORT
- MYSQL_ROOT_PASSWORD
- MYSQL_DATABASE
- MYSQL_USER
- MYSQL_PASSWORD

Service ports:

- PRODUCER_APP_PORT
- CONSUMER_APP_PORT

## Running Tests

Run producer tests:

```bash
docker compose exec producer-service pytest -q
```

Run consumer tests:

```bash
docker compose exec consumer-service pytest -q
```

Run producer integration test:

```bash
docker compose exec -e RUN_INTEGRATION_TESTS=1 producer-service pytest -q -m integration
```

Run consumer integration test:

```bash
docker compose exec -e RUN_INTEGRATION_TESTS=1 consumer-service pytest -q -m integration
```

## Logging and Error Handling

- Services log in structured timestamped lines via Python logging.
- Producer logs connection/publish outcomes and returns informative status codes.
- Consumer logs malformed messages, retry attempts, and final drop decisions.
- Malformed or non-parseable messages are acknowledged and dropped to prevent worker crashes.

## Deployment Notes

- Both custom services are containerized and stateless from an HTTP perspective.
- Persistence is externalized to MySQL.
- RabbitMQ acts as durable async transport.
- Horizontal scaling strategy:
  - Scale producer replicas behind a load balancer.
  - Scale consumer replicas as competing consumers on the same queue.
