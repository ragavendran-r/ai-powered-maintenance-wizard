# IoT Streaming Ingestion Plan

## Goal

Enable production-ready async IoT streaming ingestion from steel-plant applications using NATS JetStream, including broker configuration, durable consumer processing, validation, dead-letter handling, status visibility, tests, and documentation.

## Broker Decision

Use NATS JetStream for the first streaming ingestion implementation.

Reasons:

- Lightweight deployment model suitable for plant-edge services and hackathon demo environments.
- JetStream adds durable streams, replay, explicit acknowledgments, and durable consumers.
- Lower operational overhead than Kafka for this app's current Python/FastAPI/SQLite prototype.
- Kafka remains a future integration option if the plant already standardizes on enterprise-scale event log retention and stream processing.

References:

- NATS JetStream: https://docs.nats.io/nats-concepts/jetstream
- NATS comparison: https://docs.nats.io/nats-concepts/overview/compare-nats
- Kafka introduction: https://kafka.apache.org/23/getting-started/introduction/

## Message Broker Design

- Stream: `MW_IOT`
- Durable consumer: `maintenance-wizard-ingestor`
- Subject prefix: `steelplant.iot`
- Subjects:
  - `steelplant.iot.sensor_readings`
  - `steelplant.iot.alerts`
  - `steelplant.iot.equipment`
  - `steelplant.iot.spares`
  - `steelplant.iot.maintenance_events`
- Dead-letter subject: `steelplant.iot.dlq`

The backend should use a durable pull consumer and explicit acknowledgments. A message is acknowledged only after validation and SQLite persistence succeed. Invalid messages are published to the dead-letter subject with error metadata.

## Message Contract

Messages use a JSON envelope:

```json
{
  "message_id": "iot-msg-001",
  "schema_version": "1",
  "source": "caster-plc-gateway",
  "type": "sensor_reading",
  "timestamp": "2026-06-06T09:00:00+05:30",
  "payload": {
    "equipment_id": "CC-PUMP-03",
    "signal": "cooling_water_flow",
    "value": 1040.0,
    "unit": "m3/h",
    "threshold": 1100.0,
    "timestamp": "2026-06-06T09:00:00+05:30"
  }
}
```

Supported message types map to existing structured ingestion records:

- `equipment`
- `alert`
- `spare`
- `sensor_reading`
- `maintenance_event`

For `alert` and `sensor_reading` messages, the backend may derive `payload.id` from `source`, `equipment_id`, `signal`, and timestamp when the publisher omits it.

## Backend Changes

- Implemented streaming configuration:
  - `STREAMING_ENABLED`
  - `NATS_URL`
  - `NATS_STREAM`
  - `NATS_CONSUMER`
  - `NATS_SUBJECT_PREFIX`
  - `NATS_DLQ_SUBJECT`
  - auth/TLS settings
  - batch size, ack wait, max deliver, reconnect settings
- Added a streaming service started from FastAPI lifespan only when `STREAMING_ENABLED=true`.
- Reused `repository.add_records` for validated message persistence.
- Tracked runtime status: enabled, connected, processed count, failed count, last message timestamp, last error, stream, consumer, and subjects.
- Added `GET /api/streaming/status`.

## Frontend Changes

- Added read-only streaming ingestion status to the Ingestion view.
- Show disabled, connected, or error state.
- Show processed count, failed count, last message timestamp, and last error.

## Test Plan

- Valid sensor reading persists and appears in sensor/anomaly endpoints.
- Valid alert persists and affects dashboard/health.
- Duplicate message ID does not create duplicate records.
- Invalid payload routes through the dead-letter handler.
- Persistence failure causes retry or negative acknowledgment.
- `STREAMING_ENABLED=false` does not connect to NATS.
- `/api/streaming/status` reports disabled, connected, processed, failed, and error states.
- Existing HTTP/file/JSON ingestion tests continue to pass.
