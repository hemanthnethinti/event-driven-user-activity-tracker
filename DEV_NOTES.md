# Developer Notes

These notes describe implementation intent and practical maintenance guidance for this repository.

## Internal Design Rationale

### Why Event-Driven Instead of Direct DB Writes

Producer should return quickly and stay decoupled from persistence failures. Using RabbitMQ as the handoff boundary gives:

- lower request latency
- clearer service ownership
- independent scaling for API and worker

### Why Consumer Acks Even on Malformed Messages

Malformed payloads are considered non-recoverable in the current design. Acknowledging them avoids infinite redelivery loops and keeps throughput stable.

### Why Producer Uses RLock in Publisher

Publish path may call connect path internally while holding the lock. Re-entrant locking avoids self-deadlock in that nested call sequence.

## Key Implementation Details

### Producer Validation and Response Semantics

- Schema: UserActivityEvent in producer-service/src/app/models.py
- Validation failures are translated to 400 in main.py exception handler.
- Successful enqueue returns 202 with a minimal acknowledgement body.

### Broker Publish Durability

- Queue declared durable.
- Published message uses delivery_mode=2.

### Consumer Processing Safety

- JSON decode and schema validation are isolated in EventProcessor.process_payload.
- Insert retries are bounded by db_insert_retries.
- Timestamp stored in UTC-compatible DB format.

### Health Signaling

- Producer health checks broker path.
- Consumer health includes runtime worker + broker + db state.

## Important Code Paths

### Producer

- track_event() in producer-service/src/app/main.py
- request_validation_exception_handler() in producer-service/src/app/main.py
- RabbitMQPublisher.connect() in producer-service/src/app/rabbitmq_client.py
- RabbitMQPublisher.publish_event() in producer-service/src/app/rabbitmq_client.py
- RabbitMQPublisher.check_health() in producer-service/src/app/rabbitmq_client.py

### Consumer

- ConsumerWorker.start() and stop() in consumer-service/src/app/worker.py
- ConsumerWorker.\_run_loop() in consumer-service/src/app/worker.py
- EventProcessor.process_payload() in consumer-service/src/app/worker.py
- MySQLActivityRepository.insert_activity() in consumer-service/src/app/db.py

## Debugging Tips

### Producer Not Enqueuing

1. Check producer /health endpoint.
2. Check RabbitMQ container health and queue presence.
3. Inspect producer logs for connection retry warnings.

### Consumer Not Persisting

1. Check consumer /health endpoint details (rabbitmq_connected, mysql_connected).
2. Inspect worker logs for parse errors or DB retry exhaustion.
3. Query MySQL table directly to confirm writes.

### Integration Tests Flaking

- Use autocommit for polling reads in integration tests to avoid stale transaction snapshots.

## Common Pitfalls

- Changing payload schema in one service but not the other.
- Forgetting to declare pytest integration marker in pytest.ini.
- Editing Dockerfiles without rebuilding images before test runs.
- Using hardcoded credentials instead of env variables.

## Extension Guide

### Add a New Event Field

1. Update producer model schema.
2. Update consumer schema.
3. Update DB insert logic and migration/init SQL if needed.
4. Update unit and integration tests.

### Add Dead Letter Queue

1. Add DLX and DLQ declarations in RabbitMQ setup.
2. Publish rejects/nacks with routing to DLQ for recoverable strategy changes.
3. Add observability around DLQ depth.

### Add More Consumers

- Scale consumer-service replicas in compose or orchestration platform.
- Ensure idempotency strategy if duplicate processing risk increases.

## Rebuilding From Scratch (Conceptual)

1. Define event schema and DB table.
2. Build producer endpoint with strict validation.
3. Add broker publish client with retries.
4. Build consumer worker with processing loop and ack strategy.
5. Add repository layer with connection handling and insert retries.
6. Add health endpoints tied to dependencies.
7. Containerize all components and wire via docker-compose.
8. Add unit + integration tests.
