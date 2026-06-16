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

## Local Smoke Test

Install backend dependencies after pulling this branch:

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt
```

Start a local NATS JetStream server:

```bash
docker run --rm --name maintenance-wizard-nats \
  -p 4222:4222 \
  -p 8222:8222 \
  nats:2 -js -m 8222
```

Start the backend with streaming enabled:

```bash
cd backend
env STREAMING_ENABLED=true NATS_URL=nats://127.0.0.1:4222 \
  .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Confirm the backend has connected to NATS:

```bash
TOKEN=$(curl -s http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@plant.local","password":"DemoPass123!"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

curl http://127.0.0.1:8000/api/streaming/status \
  -H "Authorization: Bearer $TOKEN"
```

### Post A Sample NATS Alert Message

Use this quick test when the local stack is already running and `/api/streaming/status` shows `"state":"connected"`:

```bash
cd backend

.venv/bin/python - <<'PY'
import asyncio
import json
from datetime import datetime, timezone
import nats

async def main():
    nc = await nats.connect("nats://127.0.0.1:4222")
    js = nc.jetstream()

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    message = {
        "message_id": f"iot-demo-alert-{suffix}",
        "schema_version": "1",
        "source": "demo-iot-gateway",
        "type": "alert",
        "timestamp": now,
        "payload": {
            "equipment_id": "CC-PUMP-03",
            "signal": "motor_current",
            "value": 121.0,
            "unit": "A",
            "threshold": 95.0,
            "severity": "high",
            "message": "Demo NATS message: cooling pump motor current above threshold"
        }
    }

    await js.publish("steelplant.iot.alerts", json.dumps(message).encode())
    await nc.drain()

    print("Published:", message["message_id"])

asyncio.run(main())
PY
```

Verify the sample message:

```bash
curl http://127.0.0.1:8000/api/streaming/status \
  -H "Authorization: Bearer $TOKEN"
curl http://127.0.0.1:8000/api/equipment/CC-PUMP-03/health \
  -H "Authorization: Bearer $TOKEN"
```

Expected result: `processed_count` increments and `CC-PUMP-03` health shows `Demo NATS message: cooling pump motor current above threshold`.

Publish a valid sensor reading and alert:

```bash
cd backend
.venv/bin/python - <<'PY'
import asyncio
import json
from datetime import datetime
import nats

async def main():
    nc = await nats.connect("nats://127.0.0.1:4222")
    js = nc.jetstream()
    suffix = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    sensor = {
        "message_id": f"iot-live-sensor-{suffix}",
        "schema_version": "1",
        "source": "live-test-gateway",
        "type": "sensor_reading",
        "timestamp": "2026-06-06T09:30:00+05:30",
        "payload": {
            "equipment_id": "CC-PUMP-03",
            "signal": "cooling_water_flow",
            "value": 1325.0,
            "unit": "m3/h",
            "threshold": 1100.0
        }
    }
    alert = {
        "message_id": f"iot-live-alert-{suffix}",
        "schema_version": "1",
        "source": "live-test-gateway",
        "type": "alert",
        "timestamp": "2026-06-06T09:35:00+05:30",
        "payload": {
            "equipment_id": "CC-PUMP-03",
            "signal": "motor_current",
            "value": 118.0,
            "unit": "A",
            "threshold": 95.0,
            "severity": "high",
            "message": "Live NATS test: cooling pump motor current above threshold"
        }
    }
    await js.publish("steelplant.iot.sensor_readings", json.dumps(sensor).encode())
    await js.publish("steelplant.iot.alerts", json.dumps(alert).encode())
    await nc.drain()

asyncio.run(main())
PY
```

Verify the messages were consumed and persisted:

```bash
curl http://127.0.0.1:8000/api/streaming/status \
  -H "Authorization: Bearer $TOKEN"
curl http://127.0.0.1:8000/api/equipment/CC-PUMP-03/health \
  -H "Authorization: Bearer $TOKEN"
curl http://127.0.0.1:8000/api/equipment/CC-PUMP-03/sensor-readings \
  -H "Authorization: Bearer $TOKEN"
```

Expected result: `processed_count` increments, `failed_count` remains `0`, the streamed alert appears in `CC-PUMP-03` health, and the streamed sensor value appears in sensor readings.

To verify the DLQ path, publish an invalid message missing `equipment_id`; `/api/streaming/status` should show `failed_count` incremented and `last_error` set to `Payload is missing equipment_id`.
