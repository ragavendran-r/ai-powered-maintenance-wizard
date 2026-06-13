import asyncio
import json
import ssl
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Union

from app.core.config import get_settings
from app.data import repository
from app.models.schemas import LearningDatasetCreateRequest, LearningEvaluationCreateRequest, UserPublic
from app.services.learning import (
    LEARNING_JOB_SUBJECTS,
    create_dataset_snapshot,
    prepare_peft_artifacts,
    refresh_learning_examples,
    rejudge_learning_example,
    run_learning_evaluation,
)


RawLearningJobMessage = Union[bytes, str, dict[str, Any]]


class InvalidLearningJobMessage(ValueError):
    pass


@dataclass
class ProcessedLearningJob:
    job_id: str
    job_type: str
    status: str
    output_refs: dict[str, Any] = field(default_factory=dict)


def process_learning_job_message(
    raw_message: RawLearningJobMessage,
    subject: Optional[str] = None,
) -> ProcessedLearningJob:
    payload = _decode_raw_message(raw_message)
    job_id = str(payload.get("job_id") or "").strip()
    job_type = str(payload.get("job_type") or "").strip()
    if not job_id:
        raise InvalidLearningJobMessage("Learning job message is missing job_id")
    if job_type not in LEARNING_JOB_SUBJECTS:
        raise InvalidLearningJobMessage(f"Unsupported learning job type: {job_type or 'missing'}")

    job = repository.get_learning_job(job_id)
    if not job:
        raise InvalidLearningJobMessage(f"Unknown learning job_id: {job_id}")
    if job["job_type"] != job_type:
        raise InvalidLearningJobMessage(f"Learning job type mismatch for {job_id}")
    if subject and subject != job["subject"]:
        raise InvalidLearningJobMessage(f"Learning job subject mismatch for {job_id}")
    if job["status"] == "completed":
        return ProcessedLearningJob(job_id, job_type, "duplicate", job.get("output_refs") or {})

    retry_count = int(job.get("retry_count") or 0) + 1
    repository.update_learning_job_status(
        job_id,
        "running",
        output_refs={
            **(job.get("output_refs") or {}),
            "worker_started_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        },
        retry_count=retry_count,
    )
    try:
        output_refs = _execute_learning_job(job, payload)
    except Exception as exc:
        repository.update_learning_job_status(
            job_id,
            "failed",
            output_refs=job.get("output_refs") or {},
            error=str(exc),
            retry_count=retry_count,
        )
        raise

    completed = repository.update_learning_job_status(
        job_id,
        "completed",
        output_refs={
            **(job.get("output_refs") or {}),
            **output_refs,
            "worker_completed_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        },
        retry_count=retry_count,
    )
    return ProcessedLearningJob(job_id, job_type, "completed", (completed or {}).get("output_refs") or output_refs)


def build_learning_dead_letter_payload(
    raw_message: RawLearningJobMessage,
    subject: Optional[str],
    error: str,
) -> dict[str, Any]:
    return {
        "error": error,
        "subject": subject,
        "failed_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "raw_message": _raw_for_dlq(raw_message),
    }


class LearningJobWorkerService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._task: Optional[asyncio.Task] = None
        self._nc = None
        self._js = None
        self._enabled = self.settings.learning_async_enabled
        self._state = "disabled" if not self._enabled else "disconnected"
        self._processed_count = 0
        self._failed_count = 0
        self._last_message_timestamp: Optional[str] = None
        self._last_error: Optional[str] = None

    @property
    def enabled(self) -> bool:
        return self._enabled

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

    async def handle_nats_message(self, message) -> None:
        subject = getattr(message, "subject", None)
        if subject == self.settings.learning_nats_dlq_subject:
            await message.ack()
            return
        try:
            result = process_learning_job_message(message.data, subject)
            if result.status == "completed":
                self._processed_count += 1
            self._last_message_timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            await message.ack()
        except InvalidLearningJobMessage as exc:
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
                f"{self.settings.learning_nats_subject_prefix}.*",
                durable=self.settings.learning_nats_consumer,
                stream=self.settings.learning_nats_stream,
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
        stream_subjects = [
            f"{self.settings.learning_nats_subject_prefix}.*",
            self.settings.learning_nats_dlq_subject,
        ]
        config = stream_config(name=self.settings.learning_nats_stream, subjects=stream_subjects)
        try:
            await self._js.add_stream(config=config)
        except Exception as exc:
            if "already" in str(exc).lower():
                await self._js.update_stream(config=config)
            else:
                raise
        consumer = consumer_config(
            durable_name=self.settings.learning_nats_consumer,
            ack_policy=ack_policy.EXPLICIT,
            filter_subject=f"{self.settings.learning_nats_subject_prefix}.*",
            ack_wait=float(self.settings.nats_ack_wait_seconds),
            max_deliver=self.settings.nats_max_deliver,
        )
        try:
            await self._js.add_consumer(self.settings.learning_nats_stream, config=consumer)
        except Exception as exc:
            if "already" not in str(exc).lower():
                raise

    async def _publish_dlq(self, raw_message: RawLearningJobMessage, subject: Optional[str], error: str) -> None:
        if not self._js:
            return
        dlq_payload = build_learning_dead_letter_payload(raw_message, subject, error)
        await self._js.publish(self.settings.learning_nats_dlq_subject, json.dumps(dlq_payload).encode("utf-8"))


def _execute_learning_job(job: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    job_type = job["job_type"]
    input_refs = {**(job.get("input_refs") or {}), **(payload.get("input_refs") or {})}
    current_user = _job_user(job.get("requested_by") or payload.get("requested_by"))
    if job_type == "refresh_examples":
        examples = refresh_learning_examples()
        return {"example_count": len(examples)}
    if job_type == "judge_example":
        example_id = str(input_refs.get("example_id") or "")
        if not example_id:
            raise ValueError("judge_example job requires input_refs.example_id")
        example = rejudge_learning_example(example_id)
        if not example:
            raise ValueError(f"Learning example not found: {example_id}")
        return {
            "example_id": example["id"],
            "judge_score": example["judge_score"],
            "judge_label": example["judge_label"],
        }
    if job_type == "dataset_snapshot":
        request = LearningDatasetCreateRequest(
            name=str(input_refs.get("name") or f"worker-snapshot-{job['id']}"),
            description=input_refs.get("description"),
            approved_only=bool(input_refs.get("approved_only", True)),
            min_judge_score=float(input_refs.get("min_judge_score", 0.65)),
        )
        snapshot = create_dataset_snapshot(request, current_user, record_job_event=False)
        return {"dataset_id": snapshot["id"], "example_count": snapshot["example_count"]}
    if job_type == "evaluation":
        request = LearningEvaluationCreateRequest(
            dataset_id=str(input_refs.get("dataset_id") or ""),
            model_version_id=str(input_refs.get("model_version_id") or "model-local-qwen2.5-current"),
            prompt_version_id=str(input_refs.get("prompt_version_id") or "prompt-neo-default"),
            min_quality_score=float(input_refs.get("min_quality_score", 0.7)),
            notes=input_refs.get("notes"),
        )
        evaluation = run_learning_evaluation(request, current_user, record_job_event=False)
        return {
            "evaluation_run_id": evaluation["id"],
            "passed": evaluation["passed"],
            "quality_score": evaluation["metrics"].get("quality_score"),
        }
    if job_type == "peft_tuning":
        return prepare_peft_artifacts(job)
    if job_type == "adapter_registered":
        return {"message": "Adapter registration is already persisted by the API path."}
    raise ValueError(f"Unsupported learning job type: {job_type}")


def _job_user(email: Optional[str]) -> UserPublic:
    if email:
        user = repository.get_user_by_email(email)
        if user:
            return UserPublic(**user)
    return UserPublic(
        id="learning-worker",
        email=email or "learning-worker@system.local",
        display_name="Learning Worker",
        role="admin",
        is_active=True,
    )


def _decode_raw_message(raw_message: RawLearningJobMessage) -> dict[str, Any]:
    if isinstance(raw_message, dict):
        return raw_message
    try:
        text = raw_message.decode("utf-8") if isinstance(raw_message, bytes) else raw_message
        decoded = json.loads(text)
    except Exception as exc:
        raise InvalidLearningJobMessage(f"Malformed learning job JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise InvalidLearningJobMessage("Learning job message must be a JSON object")
    return decoded


def _raw_for_dlq(raw_message: RawLearningJobMessage) -> Any:
    if isinstance(raw_message, bytes):
        try:
            return raw_message.decode("utf-8")
        except UnicodeDecodeError:
            return raw_message.hex()
    return raw_message
