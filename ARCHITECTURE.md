# Architecture

## System Architecture

The system follows an event-driven pattern with explicit producer/consumer responsibilities.

```text
Client
  |
  v
Producer API (FastAPI)
  |
  v
RabbitMQ Queue: user_activity_events
  |
  v
Consumer Worker (background thread)
  |
  v
MySQL: user_activities
```

The producer only validates and enqueues events. Persistence happens asynchronously in the consumer.

## Core Components

### Producer API

Location:

- producer-service/src/app/main.py

Responsibilities:

- Accept events at POST /api/v1/events/track
- Validate payload with Pydantic model
- Return 202 on successful enqueue
- Return 400 for validation failures
- Return 503 when broker operations fail
- Expose dependency-aware /health endpoint

### RabbitMQ Publisher

Location:

- producer-service/src/app/rabbitmq_client.py

Responsibilities:

- Manage connection/channel lifecycle
- Declare durable queue
- Publish persistent messages (delivery_mode=2)
- Retry broker connection attempts

Implementation note:

- Uses a re-entrant lock around connection and publish paths to prevent concurrent connection races.

### Consumer Service

Locations:

- consumer-service/src/app/main.py
- consumer-service/src/app/worker.py

Responsibilities:

- Start worker loop in application lifespan
- Continuously consume from queue
- Process each payload and persist to MySQL
- Ack messages after processing attempt
- Expose /health with runtime dependency state

### Event Processor

Location:

- consumer-service/src/app/worker.py (EventProcessor)

Responsibilities:

- Deserialize message body
- Validate schema
- Retry transient persistence failures
- Drop malformed/unrecoverable events safely with logs

### Repository Layer

Location:

- consumer-service/src/app/db.py

Responsibilities:

- Connect/ping MySQL
- Insert activity rows
- Normalize timestamps to UTC naive DATETIME for storage
- Close connections during shutdown

## Request Flow

1. Client posts JSON event to producer endpoint.
2. Producer validates request and serializes payload.
3. Producer publishes payload to user_activity_events queue.
4. Consumer fetches message from queue.
5. EventProcessor validates and forwards to repository.
6. Repository inserts into user_activities table.
7. Consumer acknowledges message.

## Health and Observability

### Producer Health

- Verifies RabbitMQ connectivity using passive queue check.
- Returns 200 when broker path is operational.

### Consumer Health

- Reports worker running state.
- Reports RabbitMQ connected state.
- Reports MySQL connected state.
- Returns 503 when degraded.

### Logging

- Standardized timestamped logs in both services.
- Important lifecycle events:
  - connection success/failure
  - publish and persist results
  - retry attempts
  - malformed message drops

## Failure Handling

### Invalid API Payload

- Caught by FastAPI validation handling in producer.
- Returns 400 with detailed validation error list.

### RabbitMQ Unavailable

- Producer retries connection then fails request with 503.
- Consumer loop logs failures, waits, and reconnects.

### Malformed Queue Message

- Consumer logs parse/validation failure.
- Message is acknowledged and dropped to avoid poison-loop crashes.

### Database Failures

- Consumer retries inserts with configurable backoff.
- If retries exhausted, event is dropped and logged.

## Data Model

Table: user_activities

- id: INT AUTO_INCREMENT PRIMARY KEY
- user_id: INT NOT NULL
- event_type: VARCHAR(50) NOT NULL
- timestamp: DATETIME NOT NULL
- metadata: JSON
- created_at: TIMESTAMP DEFAULT CURRENT_TIMESTAMP

## Scalability Considerations

- Producer can be scaled horizontally behind an API gateway.
- Consumer can scale as competing consumers on the same queue.
- Queue depth can be used as a backpressure signal.
- For stricter durability requirements, add dead-letter exchanges and replay tooling.

## Deployment Topology

Current local/dev topology is defined in docker-compose.yml with:

- rabbitmq
- mysql
- producer-service
- consumer-service

All services include health checks and dependency wiring via environment variables.
