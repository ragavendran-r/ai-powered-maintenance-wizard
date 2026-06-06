import asyncio
import json
import ssl
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha1
from typing import Any, Optional, Union

from app.core.config import get_settings
from app.data import repository
from app.models.schemas import (
    Alert,
    Equipment,
    IoTMessageEnvelope,
    MaintenanceEvent,
    SensorReading,
    SparePart,
    StreamingStatus,
)


SUBJECT_TYPES = {
    "equipment": "equipment",
    "alerts": "alert",
    "spares": "spare",
    "sensor_readings": "sensor_reading",
    "maintenance_events": "maintenance_event",
}
TABLE_BY_TYPE = {
    "equipment": "equipment",
    "alert": "alerts",
    "spare": "spares",
    "sensor_reading": "sensor_readings",
    "maintenance_event": "maintenance_events",
}
MODEL_BY_TYPE = {
    "equipment": Equipment,
    "alert": Alert,
    "spare": SparePart,
    "sensor_reading": SensorReading,
    "maintenance_event": MaintenanceEvent,
}


class InvalidIoTMessage(ValueError):
    pass


@dataclass
class ProcessedIoTMessage:
    message_id: str
    message_type: str
    status: str
    counts: dict[str, int] = field(default_factory=dict)


def streaming_subjects(prefix: str) -> list[str]:
    return [f"{prefix}.{subject}" for subject in SUBJECT_TYPES]


RawIoTMessage = Union[bytes, str, dict[str, Any]]


def process_iot_message(raw_message: RawIoTMessage, subject: Optional[str] = None) -> ProcessedIoTMessage:
    payload = _decode_raw_message(raw_message)
    envelope = IoTMessageEnvelope.model_validate(payload)
    _validate_timestamp(envelope.timestamp, "timestamp")

    existing = repository.get_streaming_message(envelope.message_id)
    if existing and existing["status"] == "processed":
        return ProcessedIoTMessage(envelope.message_id, envelope.type, "duplicate")

    record = _validated_record(envelope)
    table = TABLE_BY_TYPE[envelope.type]
    counts = repository.add_records({table: [record]})
    repository.save_streaming_message(envelope.message_id, envelope.source, envelope.type, subject, "processed")
    return ProcessedIoTMessage(envelope.message_id, envelope.type, "processed", counts)


def build_dead_letter_payload(
    raw_message: RawIoTMessage,
    subject: Optional[str],
    error: str,
) -> dict[str, Any]:
    return {
        "error": error,
        "subject": subject,
        "failed_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "raw_message": _raw_for_dlq(raw_message),
    }


class StreamingIngestionService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._task: Optional[asyncio.Task] = None
        self._nc = None
        self._js = None
        self._enabled = self.settings.streaming_enabled
        self._state = "disabled" if not self._enabled else "disconnected"
        self._processed_count = 0
        self._failed_count = 0
        self._last_message_timestamp: Optional[str] = None
        self._last_error: Optional[str] = None

    async def start(self) -> None:
        if not self._enabled:
            self._state = "disabled"
            return
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._nc:
            await self._nc.close()

    def status(self) -> StreamingStatus:
        return StreamingStatus(
            enabled=self._enabled,
            state=self._state,
            stream=self.settings.nats_stream,
            consumer=self.settings.nats_consumer,
            subjects=streaming_subjects(self.settings.nats_subject_prefix),
            processed_count=self._processed_count,
            failed_count=self._failed_count,
            last_message_timestamp=self._last_message_timestamp,
            last_error=self._last_error,
        )

    async def handle_nats_message(self, message) -> None:
        subject = getattr(message, "subject", None)
        if subject == self.settings.nats_dlq_subject:
            await message.ack()
            return
        try:
            result = process_iot_message(message.data, subject)
            if result.status == "processed":
                self._processed_count += 1
            self._last_message_timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            await message.ack()
        except InvalidIoTMessage as exc:
            self._failed_count += 1
            self._last_error = str(exc)
            await self._publish_dlq(message.data, subject, str(exc))
            await message.ack()
        except Exception as exc:
            self._failed_count += 1
            self._last_error = str(exc)
            await message.nak()

    async def _run(self) -> None:
        try:
            import nats
            from nats.js.api import AckPolicy, ConsumerConfig, StreamConfig
        except ImportError as exc:
            self._state = "error"
            self._last_error = f"nats-py is not installed: {exc}"
            return

        try:
            connect_kwargs: dict[str, Any] = {
                "servers": [self.settings.nats_url],
                "max_reconnect_attempts": self.settings.nats_max_reconnect_attempts,
                "reconnect_time_wait": self.settings.nats_reconnect_time_wait_seconds,
            }
            if self.settings.nats_auth_token:
                connect_kwargs["token"] = self.settings.nats_auth_token
            if self.settings.nats_credentials_path:
                connect_kwargs["user_credentials"] = str(self.settings.nats_credentials_path)
            if self.settings.nats_tls_enabled:
                connect_kwargs["tls"] = ssl.create_default_context()

            self._nc = await nats.connect(**connect_kwargs)
            self._js = self._nc.jetstream()
            await self._ensure_stream_and_consumer(StreamConfig, ConsumerConfig, AckPolicy)
            subscription = await self._js.pull_subscribe(
                f"{self.settings.nats_subject_prefix}.*",
                durable=self.settings.nats_consumer,
                stream=self.settings.nats_stream,
            )
            self._state = "connected"
            while True:
                try:
                    messages = await subscription.fetch(self.settings.nats_batch_size, timeout=1)
                except TimeoutError:
                    continue
                except asyncio.TimeoutError:
                    continue
                for message in messages:
                    await self.handle_nats_message(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._state = "error"
            self._last_error = str(exc)

    async def _ensure_stream_and_consumer(self, stream_config, consumer_config, ack_policy) -> None:
        subjects = streaming_subjects(self.settings.nats_subject_prefix)
        stream_subjects = [*subjects, self.settings.nats_dlq_subject]
        config = stream_config(name=self.settings.nats_stream, subjects=stream_subjects)
        try:
            await self._js.add_stream(config=config)
        except Exception as exc:
            if "already" in str(exc).lower():
                await self._js.update_stream(config=config)
            else:
                raise
        consumer = consumer_config(
            durable_name=self.settings.nats_consumer,
            ack_policy=ack_policy.EXPLICIT,
            filter_subject=f"{self.settings.nats_subject_prefix}.*",
            ack_wait=float(self.settings.nats_ack_wait_seconds),
            max_deliver=self.settings.nats_max_deliver,
        )
        try:
            await self._js.add_consumer(self.settings.nats_stream, config=consumer)
        except Exception as exc:
            if "already" not in str(exc).lower():
                raise

    async def _publish_dlq(self, raw_message: RawIoTMessage, subject: Optional[str], error: str) -> None:
        if not self._js:
            return
        dlq_payload = build_dead_letter_payload(raw_message, subject, error)
        await self._js.publish(self.settings.nats_dlq_subject, json.dumps(dlq_payload).encode("utf-8"))


def _decode_raw_message(raw_message: RawIoTMessage) -> dict[str, Any]:
    if isinstance(raw_message, dict):
        return raw_message
    try:
        text = raw_message.decode("utf-8") if isinstance(raw_message, bytes) else raw_message
        decoded = json.loads(text)
    except Exception as exc:
        raise InvalidIoTMessage(f"Malformed JSON message: {exc}") from exc
    if not isinstance(decoded, dict):
        raise InvalidIoTMessage("IoT message must be a JSON object")
    return decoded


def _validated_record(envelope: IoTMessageEnvelope) -> dict[str, Any]:
    record = dict(envelope.payload)
    if envelope.type in {"alert", "sensor_reading"}:
        record.setdefault("timestamp", envelope.timestamp)
        record.setdefault("id", _derived_record_id(envelope, record))
    if envelope.type != "equipment":
        equipment_id = record.get("equipment_id")
        if not equipment_id:
            raise InvalidIoTMessage("Payload is missing equipment_id")
        if not repository.get_equipment(str(equipment_id)):
            raise InvalidIoTMessage(f"Unknown equipment_id: {equipment_id}")
    if "timestamp" in record:
        _validate_timestamp(str(record["timestamp"]), "payload.timestamp")
    try:
        return MODEL_BY_TYPE[envelope.type](**record).model_dump()
    except Exception as exc:
        raise InvalidIoTMessage(f"Invalid {envelope.type} payload: {exc}") from exc


def _validate_timestamp(value: str, field: str) -> None:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidIoTMessage(f"Invalid {field}: {value}") from exc


def _derived_record_id(envelope: IoTMessageEnvelope, payload: dict[str, Any]) -> str:
    raw = "|".join(
        [
            envelope.source,
            envelope.type,
            str(payload.get("equipment_id", "")),
            str(payload.get("signal", "")),
            str(payload.get("timestamp", envelope.timestamp)),
        ]
    )
    prefix = "ALT" if envelope.type == "alert" else "SR"
    return f"{prefix}-IOT-{sha1(raw.encode('utf-8')).hexdigest()[:12].upper()}"


def _raw_for_dlq(raw_message: RawIoTMessage) -> Any:
    if isinstance(raw_message, bytes):
        return raw_message.decode("utf-8", errors="replace")
    return raw_message
