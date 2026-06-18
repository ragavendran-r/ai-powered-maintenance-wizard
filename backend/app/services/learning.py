from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shlex
import ssl
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.core.config import get_settings
from app.data import repository
from app.models.schemas import (
    LearningDatasetCreateRequest,
    LearningEvaluationCreateRequest,
    LearningJudgeResult,
    LearningJob,
    LearningModelDeploymentCreateRequest,
    LearningModelPromotionRequest,
    LearningModelRollbackRequest,
    LearningModelVersionCreateRequest,
    LearningPeftJobCreateRequest,
    RagEmbeddingProfile,
    RagEmbeddingProfileCreateRequest,
    RagMigrationPlan,
    RagMigrationRequest,
    RagReindexRequest,
    LearningSummary,
    UserPublic,
)
from app.services.ai_client import active_llm_serving_config, configured_llm_client
from app.services.adapter_runtime import execute_adapter_deployment
from app.services.artifact_store import artifact_store_status, store_learning_artifact_file
from app.services.embeddings import current_embedding_profile, embedding_profile_id, supported_embedding_provider
from app.services.runtime_env import env_file_values_for
from app.services.vector_store import (
    plan_qdrant_migration,
    sync_learning_examples_index,
    vector_store_status,
)


APPROVED_FEEDBACK_STATUSES = {"accepted", "corrected"}
MAX_EXAMPLE_TEXT_CHARS = 1800
TRAINING_WORTHY_SCORE = 0.65
LEARNING_JOB_SUBJECTS = {
    "refresh_examples": "example.created",
    "judge_example": "judge.requested",
    "dataset_snapshot": "dataset.requested",
    "evaluation": "evaluation.requested",
    "peft_tuning": "peft.requested",
    "adapter_deployment": "adapter.deployment.requested",
    "adapter_registered": "adapter.registered",
    "model_promotion": "adapter.promoted",
    "rag_reindex": "rag.reindex.requested",
    "rag_embedding_profile": "rag.embedding.profile.requested",
    "rag_migration": "rag.migration.requested",
    "artifact_cleanup": "artifact.cleanup.requested",
}


def learning_stream_subjects(subject_prefix: str) -> list[str]:
    return [f"{subject_prefix}.>"]


def record_assistant_interaction(
    *,
    assistant: str,
    interaction_type: str,
    prompt: str,
    response: str,
    provider: str,
    used_live_provider: bool,
    current_user: Optional[UserPublic] = None,
    equipment_id: Optional[str] = None,
    work_order_id: Optional[str] = None,
    source_refs: Optional[list[dict[str, Any]]] = None,
    approved_for_learning: bool = False,
    outcome_status: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    if not prompt.strip() or not response.strip():
        return None
    try:
        return repository.save_learning_interaction(
            {
                "assistant": assistant,
                "interaction_type": interaction_type,
                "user_id": current_user.id if current_user else None,
                "user_role": current_user.role if current_user else None,
                "equipment_id": equipment_id,
                "work_order_id": work_order_id,
                "prompt": _clip(prompt),
                "response": _clip(response),
                "provider": provider,
                "used_live_provider": used_live_provider,
                "source_refs": source_refs or [],
                "approved_for_learning": approved_for_learning,
                "outcome_status": outcome_status,
            }
        )
    except Exception:
        return None


def refresh_learning_examples(*, include_documents: bool = True, include_interactions: bool = True) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    examples.extend(_examples_from_feedback())
    examples.extend(_examples_from_labels())
    examples.extend(_examples_from_work_orders())
    examples.extend(_examples_from_rca_cases())
    if include_documents:
        examples.extend(_examples_from_documents())
    if include_interactions:
        examples.extend(_examples_from_approved_interactions())
    sync_learning_examples_index(examples, min_judge_score=TRAINING_WORTHY_SCORE)
    return examples


def learning_context_for_asset(equipment_id: str, limit: int = 5) -> list[str]:
    examples = repository.list_learning_examples(
        approved_only=True,
        equipment_id=equipment_id,
        min_judge_score=TRAINING_WORTHY_SCORE,
        limit=limit,
    )
    notes: list[str] = []
    for example in examples:
        expected = " ".join(example["expected_output"].split())
        notes.append(f"{example['source_type']}: {expected[:220]}")
    return notes


def create_dataset_snapshot(
    request: LearningDatasetCreateRequest,
    current_user: UserPublic,
    *,
    record_job_event: bool = True,
) -> dict[str, Any]:
    examples = repository.list_learning_examples(
        approved_only=True if request.approved_only else None,
        min_judge_score=request.min_judge_score,
        limit=1000,
    )
    lines = [_example_to_jsonl_line(example) for example in examples]
    snapshot = repository.create_learning_dataset_snapshot(
        {
            "name": request.name,
            "description": request.description,
            "approved_only": request.approved_only,
            "example_count": len(lines),
            "jsonl_content": "\n".join(lines),
            "created_by": current_user.email,
        }
    )
    if record_job_event:
        record_learning_job(
            "dataset_snapshot",
            current_user,
            input_refs={
                "approved_only": request.approved_only,
                "min_judge_score": request.min_judge_score,
            },
            output_refs={
                "dataset_id": snapshot["id"],
                "example_count": snapshot["example_count"],
            },
            status="completed",
        )
    return snapshot


def learning_summary() -> LearningSummary:
    return LearningSummary(
        counts=repository.learning_counts(),
        recent_examples=repository.list_learning_examples(limit=25),
        recent_snapshots=repository.list_learning_dataset_snapshots(limit=10),
        model_versions=repository.list_learning_model_versions(),
        prompt_versions=repository.list_learning_prompt_versions(),
        evaluation_runs=repository.list_learning_evaluation_runs(limit=10),
        recent_jobs=repository.list_learning_jobs(limit=10),
        recent_artifacts=repository.list_learning_artifacts(limit=10),
        recent_promotions=repository.list_learning_model_promotions(limit=10),
        recent_deployments=repository.list_learning_model_deployments(limit=10),
        serving_model=active_llm_serving_config().public_dict(),
        artifact_store=artifact_store_status(),
        peft_trainer=peft_trainer_status(),
        vector_store=vector_store_status(),
    )


def peft_trainer_status(settings: Optional[Any] = None) -> dict[str, Any]:
    settings = settings or get_settings()
    command = str(getattr(settings, "learning_peft_trainer_command", "") or "").strip()
    output_dir = getattr(settings, "learning_peft_output_dir", None)
    peft_env = _peft_env_overrides()
    return {
        "mode": "external_command" if command else "prepared_artifacts",
        "configured": bool(command),
        "timeout_seconds": int(getattr(settings, "learning_peft_trainer_timeout_seconds", 900) or 900),
        "output_dir": str(output_dir) if output_dir else None,
        "model_source": peft_env.get("MW_PEFT_MODEL_SOURCE") or peft_env.get("MW_PEFT_HF_MODEL_ID"),
        "quantization": peft_env.get("MW_PEFT_QUANTIZATION"),
    }


def register_model_version(request: LearningModelVersionCreateRequest, current_user: UserPublic) -> dict[str, Any]:
    notes = request.notes or ""
    audit_note = f"Registered by {current_user.email}"
    model = repository.save_learning_model_version(
        {
            "provider": request.provider,
            "model_name": request.model_name,
            "base_model": request.base_model,
            "adapter_path": request.adapter_path,
            "status": request.status,
            "notes": f"{notes}\n{audit_note}".strip(),
        }
    )
    record_learning_job(
        "adapter_registered",
        current_user,
        input_refs={
            "provider": request.provider,
            "model_name": request.model_name,
            "base_model": request.base_model,
            "adapter_path": request.adapter_path,
        },
        output_refs={"model_version_id": model["id"], "status": model["status"]},
        status="completed",
    )
    return model


def run_learning_evaluation(
    request: LearningEvaluationCreateRequest,
    current_user: UserPublic,
    *,
    record_job_event: bool = True,
) -> dict[str, Any]:
    snapshot = repository.get_learning_dataset_snapshot(request.dataset_id)
    if not snapshot:
        raise ValueError("Learning dataset not found")
    model_ids = {model["id"] for model in repository.list_learning_model_versions()}
    if request.model_version_id not in model_ids:
        raise ValueError("Learning adapter version not found")
    prompt_ids = {prompt["id"] for prompt in repository.list_learning_prompt_versions()}
    if request.prompt_version_id not in prompt_ids:
        raise ValueError("Learning prompt version not found")

    records = _jsonl_records(snapshot["jsonl_content"])
    metrics = _evaluation_metrics(records, snapshot)
    passed = bool(records) and metrics["quality_score"] >= request.min_quality_score and metrics["average_judge_score"] >= TRAINING_WORTHY_SCORE
    notes = request.notes or (
        f"Dataset quality evaluation by {current_user.email}. "
        f"Pass threshold={request.min_quality_score}; quality={metrics['quality_score']}."
    )
    run = repository.save_learning_evaluation_run(
        {
            "dataset_id": request.dataset_id,
            "model_version_id": request.model_version_id,
            "prompt_version_id": request.prompt_version_id,
            "metrics": metrics,
            "notes": notes,
            "passed": passed,
        }
    )
    if record_job_event:
        record_learning_job(
            "evaluation",
            current_user,
            input_refs={
                "dataset_id": request.dataset_id,
                "model_version_id": request.model_version_id,
                "prompt_version_id": request.prompt_version_id,
                "min_quality_score": request.min_quality_score,
            },
            output_refs={"evaluation_run_id": run["id"], "passed": run["passed"], "quality_score": metrics["quality_score"]},
            status="completed",
        )
    return run


def promote_model_version(request: LearningModelPromotionRequest, current_user: UserPublic) -> dict[str, Any]:
    model = _validated_promotable_model(request.model_version_id)
    evaluation = _validated_promotion_evaluation(
        request.evaluation_run_id,
        request.model_version_id,
    )
    deployment = _ensure_runtime_deployment_for_promotion(model, request, current_user)
    previous_active = next(
        (item for item in repository.list_learning_model_versions() if item["status"] == "active" and item["id"] != model["id"]),
        None,
    )
    for active_model in repository.list_learning_model_versions():
        if active_model["status"] == "active" and active_model["id"] != model["id"]:
            repository.set_learning_model_status(
                active_model["id"],
                "retired",
                _append_note(active_model.get("notes"), f"Retired by promotion of {model['id']} by {current_user.email}."),
            )
    promoted = repository.set_learning_model_status(
        model["id"],
        "active",
        _append_note(model.get("notes"), f"Promoted by {current_user.email} using evaluation {evaluation['id']}. {request.notes or ''}"),
    )
    promotion = repository.save_learning_model_promotion(
        {
            "model_version_id": model["id"],
            "previous_active_model_id": previous_active["id"] if previous_active else None,
            "evaluation_run_id": evaluation["id"],
            "dataset_id": evaluation["dataset_id"],
            "prompt_version_id": evaluation["prompt_version_id"],
            "action": "promote",
            "reviewer_email": current_user.email,
            "notes": request.notes,
        }
    )
    record_learning_job(
        "model_promotion",
        current_user,
        input_refs={
            "model_version_id": model["id"],
            "evaluation_run_id": evaluation["id"],
            "action": "promote",
        },
        output_refs={
            "promotion_id": promotion["id"],
            "deployment_id": deployment["id"] if deployment else None,
            "active_model_version_id": promoted["id"] if promoted else model["id"],
            "previous_active_model_id": previous_active["id"] if previous_active else None,
        },
        status="completed",
    )
    return promotion


def rollback_model_version(request: LearningModelRollbackRequest, current_user: UserPublic) -> dict[str, Any]:
    model = repository.get_learning_model_version(request.target_model_version_id)
    if not model:
        raise ValueError("Learning adapter version not found")
    evaluation = _validated_promotion_evaluation(
        request.evaluation_run_id,
        request.target_model_version_id,
    )
    deployment = _validated_runtime_deployment(model)
    previous_active = next(
        (item for item in repository.list_learning_model_versions() if item["status"] == "active" and item["id"] != model["id"]),
        None,
    )
    for active_model in repository.list_learning_model_versions():
        if active_model["status"] == "active" and active_model["id"] != model["id"]:
            repository.set_learning_model_status(
                active_model["id"],
                "retired",
                _append_note(active_model.get("notes"), f"Retired by rollback to {model['id']} by {current_user.email}."),
            )
    restored = repository.set_learning_model_status(
        model["id"],
        "active",
        _append_note(model.get("notes"), f"Rollback target activated by {current_user.email} using evaluation {evaluation['id']}. {request.notes or ''}"),
    )
    promotion = repository.save_learning_model_promotion(
        {
            "model_version_id": model["id"],
            "previous_active_model_id": previous_active["id"] if previous_active else None,
            "evaluation_run_id": evaluation["id"],
            "dataset_id": evaluation["dataset_id"],
            "prompt_version_id": evaluation["prompt_version_id"],
            "action": "rollback",
            "reviewer_email": current_user.email,
            "notes": request.notes,
        }
    )
    record_learning_job(
        "model_promotion",
        current_user,
        input_refs={
            "model_version_id": model["id"],
            "evaluation_run_id": evaluation["id"],
            "action": "rollback",
        },
        output_refs={
            "promotion_id": promotion["id"],
            "deployment_id": deployment["id"] if deployment else None,
            "active_model_version_id": restored["id"] if restored else model["id"],
            "previous_active_model_id": previous_active["id"] if previous_active else None,
        },
        status="completed",
    )
    return promotion


def queue_adapter_deployment_job(
    model_version_id: str,
    request: LearningModelDeploymentCreateRequest,
    current_user: UserPublic,
) -> LearningJob:
    model = repository.get_learning_model_version(model_version_id)
    if not model:
        raise ValueError("Learning adapter version not found")
    if model.get("status") == "active":
        raise ValueError("Active adapter versions are already serving and cannot be deployed as candidates")
    artifact_uri = request.artifact_uri or model.get("adapter_path")
    _validate_artifact_reference(artifact_uri, request.artifact_hash)
    input_refs = {
        "model_version_id": model["id"],
        "runtime_provider": request.runtime_provider,
        "served_model_name": request.served_model_name or model.get("model_name"),
        "base_url": request.base_url,
        "artifact_uri": artifact_uri,
        "artifact_hash": request.artifact_hash,
        "notes": request.notes,
    }
    job = repository.save_learning_job(
        {
            "job_type": "adapter_deployment",
            "subject": _learning_subject("adapter_deployment"),
            "status": "queued",
            "requested_by": current_user.email,
            "input_refs": input_refs,
        }
    )
    settings = get_settings()
    if not settings.learning_async_enabled:
        job = repository.update_learning_job_status(
            job["id"],
            "queued",
            output_refs={
                "dispatch": "disabled",
                "message": "Set LEARNING_ASYNC_ENABLED=true to publish this deployment job to NATS JetStream.",
            },
        ) or job
        return LearningJob(**job)
    try:
        asyncio.run(_publish_learning_job(job))
    except Exception as exc:
        failed_job = repository.update_learning_job_status(job["id"], "failed", error=str(exc))
        return LearningJob(**(failed_job or job))
    published_job = repository.update_learning_job_status(
        job["id"],
        "published",
        output_refs={
            "dispatch": "published",
            "stream": settings.learning_nats_stream,
            "subject": job["subject"],
        },
    )
    return LearningJob(**(published_job or job))


def _validated_promotable_model(model_version_id: str) -> dict[str, Any]:
    model = repository.get_learning_model_version(model_version_id)
    if not model:
        raise ValueError("Learning adapter version not found")
    if model["status"] == "active":
        raise ValueError("Learning adapter version is already active")
    if not model.get("adapter_path"):
        raise ValueError("Adapter promotion requires an adapter_path or registered adapter artifact URI")
    return model


def _validated_runtime_deployment(model: dict[str, Any]) -> Optional[dict[str, Any]]:
    if not get_settings().learning_runtime_deployment_required:
        return repository.get_verified_learning_model_deployment(model["id"])
    if not model.get("adapter_path"):
        return None
    deployment = repository.get_verified_learning_model_deployment(model["id"])
    if not deployment:
        raise ValueError("Adapter promotion requires a runtime-loaded deployment for this adapter version")
    artifact_uri = deployment.get("artifact_uri")
    if artifact_uri and artifact_uri != model.get("adapter_path"):
        raise ValueError("Verified runtime deployment artifact URI does not match the model adapter path")
    _validate_artifact_reference(artifact_uri, deployment.get("artifact_hash"))
    return deployment


def _ensure_runtime_deployment_for_promotion(
    model: dict[str, Any],
    request: LearningModelPromotionRequest,
    current_user: UserPublic,
) -> Optional[dict[str, Any]]:
    try:
        return _validated_runtime_deployment(model)
    except ValueError as exc:
        if "runtime-loaded deployment" not in str(exc):
            raise

    artifact_uri = request.artifact_uri or model.get("adapter_path")
    deployment_job = repository.save_learning_job(
        {
            "job_type": "adapter_deployment",
            "subject": _learning_subject("adapter_deployment"),
            "status": "running",
            "requested_by": current_user.email,
            "input_refs": {
                "model_version_id": model["id"],
                "runtime_provider": request.runtime_provider,
                "served_model_name": request.served_model_name or model.get("model_name"),
                "base_url": request.base_url,
                "artifact_uri": artifact_uri,
                "artifact_hash": request.artifact_hash,
                "notes": _append_note(request.notes, "Runtime deployment attempted during promotion."),
            },
        }
    )
    try:
        result = execute_adapter_deployment(deployment_job)
    except Exception as exc:
        repository.update_learning_job_status(deployment_job["id"], "failed", error=str(exc))
        raise ValueError(f"Adapter promotion requires a runtime-loaded deployment: {exc}") from exc
    repository.update_learning_job_status(
        deployment_job["id"],
        "completed",
        output_refs={
            "deployment_id": result["deployment_id"],
            "runtime_provider": result["runtime_provider"],
            "served_model_name": result["served_model_name"],
            "health_status": result["health_status"],
        },
    )
    return _validated_runtime_deployment(model)


def _validated_promotion_evaluation(evaluation_run_id: str, model_version_id: str) -> dict[str, Any]:
    evaluation = repository.get_learning_evaluation_run(evaluation_run_id)
    if not evaluation:
        raise ValueError("Learning evaluation run not found")
    if not evaluation["passed"]:
        raise ValueError("Adapter promotion requires a passed evaluation run")
    if evaluation.get("model_version_id") != model_version_id:
        raise ValueError("Evaluation run does not match the requested adapter version")
    if not evaluation.get("dataset_id") or not repository.get_learning_dataset_snapshot(evaluation["dataset_id"]):
        raise ValueError("Promotion evaluation is missing a persisted dataset snapshot")
    if not evaluation.get("prompt_version_id") or not repository.get_learning_prompt_version(evaluation["prompt_version_id"]):
        raise ValueError("Promotion evaluation is missing a persisted prompt version")
    return evaluation


def _append_note(existing: Optional[str], note: str) -> str:
    return "\n".join(part for part in [existing, note.strip()] if part)


def _validate_artifact_reference(artifact_uri: Optional[str], artifact_hash: Optional[str]) -> None:
    if not artifact_uri and not artifact_hash:
        return
    artifacts = repository.list_learning_artifacts(limit=1000)
    if not artifacts:
        return
    uri_matches = [artifact for artifact in artifacts if artifact_uri and artifact_uri in _artifact_reference_uris(artifact)]
    hash_matches = [artifact for artifact in artifacts if artifact_hash and artifact.get("content_hash") == artifact_hash]
    if artifact_hash and not hash_matches:
        raise ValueError("Adapter artifact hash does not match a persisted learning artifact")
    if artifact_uri and artifact_hash and uri_matches:
        if not any(artifact.get("content_hash") == artifact_hash for artifact in uri_matches):
            raise ValueError("Adapter artifact hash does not match the artifact URI")
    if artifact_uri and artifact_hash and hash_matches:
        if not any(artifact_uri in _artifact_reference_uris(artifact) for artifact in hash_matches):
            raise ValueError("Adapter artifact URI does not match the artifact hash")


def _artifact_reference_uris(artifact: dict[str, Any]) -> set[str]:
    metadata = artifact.get("metadata") or {}
    return {str(value) for value in {artifact.get("uri"), metadata.get("local_path")} if value}


def record_learning_job(
    job_type: str,
    current_user: UserPublic,
    *,
    input_refs: Optional[dict[str, Any]] = None,
    output_refs: Optional[dict[str, Any]] = None,
    status: str = "completed",
    error: Optional[str] = None,
) -> dict[str, Any]:
    return repository.save_learning_job(
        {
            "job_type": job_type,
            "subject": _learning_subject(job_type),
            "status": status,
            "requested_by": current_user.email,
            "input_refs": input_refs or {},
            "output_refs": output_refs or {},
            "error": error,
        }
    )


def queue_peft_tuning_job(request: LearningPeftJobCreateRequest, current_user: UserPublic) -> LearningJob:
    _validate_dataset_model_prompt(request.dataset_id, request.model_version_id, request.prompt_version_id)
    job = repository.save_learning_job(
        {
            "job_type": "peft_tuning",
            "subject": _learning_subject("peft_tuning"),
            "status": "queued",
            "requested_by": current_user.email,
            "input_refs": {
                "dataset_id": request.dataset_id,
                "model_version_id": request.model_version_id,
                "prompt_version_id": request.prompt_version_id,
                "adapter_name": request.adapter_name,
                "base_model": request.base_model,
                "training_config": request.training_config,
                "notes": request.notes,
            },
        }
    )
    settings = get_settings()
    if not settings.learning_async_enabled:
        job = repository.update_learning_job_status(
            job["id"],
            "queued",
            output_refs={
                "dispatch": "disabled",
                "message": "Set LEARNING_ASYNC_ENABLED=true to publish this job to NATS JetStream.",
            },
        ) or job
        return LearningJob(**job)
    try:
        asyncio.run(_publish_learning_job(job))
    except Exception as exc:
        failed_job = repository.update_learning_job_status(job["id"], "failed", error=str(exc))
        return LearningJob(**(failed_job or job))
    published_job = repository.update_learning_job_status(
        job["id"],
        "published",
        output_refs={
            "dispatch": "published",
            "stream": settings.learning_nats_stream,
            "subject": job["subject"],
        },
    )
    return LearningJob(**(published_job or job))


def reindex_rag_vectors(current_user: UserPublic) -> LearningJob:
    return reindex_rag_vectors_with_request(RagReindexRequest(), current_user)


def reindex_rag_vectors_with_request(request: RagReindexRequest, current_user: UserPublic) -> LearningJob:
    profile = current_embedding_profile()
    result = repository.rebuild_all_document_chunks(
        collection_name=request.target_collection,
        recreate_collection=request.recreate_collection,
    )
    job = record_learning_job(
        "rag_reindex",
        current_user,
        input_refs={
            "reason": "manual_reindex",
            "notes": request.notes,
            "target_collection": request.target_collection,
            "recreate_collection": request.recreate_collection,
            "embedding_profile_id": profile.id,
            "vector_store": result["index_result"].get("store"),
            "collection": result["index_result"].get("collection"),
        },
        output_refs=result,
        status="completed",
    )
    return LearningJob(**job)


def create_rag_embedding_profile(request: RagEmbeddingProfileCreateRequest, current_user: UserPublic) -> RagEmbeddingProfile:
    if not supported_embedding_provider(request.provider):
        raise ValueError(f"Embedding provider {request.provider} is not supported by this runtime")
    profile_id = embedding_profile_id(
        request.provider,
        request.model,
        request.version,
        request.dimensions,
        request.distance,
    )
    profile = repository.save_rag_embedding_profile(
        {
            "id": profile_id,
            "provider": request.provider,
            "model": request.model,
            "version": request.version,
            "dimensions": request.dimensions,
            "distance": request.distance,
            "status": "candidate",
            "notes": request.notes,
            "metadata": {
                **request.metadata,
                "created_by": current_user.email,
            },
        }
    )
    record_learning_job(
        "rag_embedding_profile",
        current_user,
        input_refs={"profile_id": profile_id, "action": "register"},
        output_refs={"profile": profile},
        status="completed",
    )
    return RagEmbeddingProfile(**profile)


def activate_rag_embedding_profile(profile_id: str, current_user: UserPublic) -> LearningJob:
    profile = repository.get_rag_embedding_profile(profile_id)
    if not profile:
        raise ValueError(f"RAG embedding profile {profile_id} was not found")
    if not supported_embedding_provider(profile["provider"]):
        raise ValueError(f"Embedding provider {profile['provider']} is not supported by this runtime")
    active = repository.activate_rag_embedding_profile(profile_id)
    job = record_learning_job(
        "rag_embedding_profile",
        current_user,
        input_refs={"profile_id": profile_id, "action": "activate"},
        output_refs={
            "profile": active,
            "vector_store": vector_store_status(),
            "migration_required": True,
        },
        status="completed",
    )
    return LearningJob(**job)


def preview_rag_migration(request: RagMigrationRequest) -> RagMigrationPlan:
    return RagMigrationPlan(**plan_qdrant_migration(request.profile_id, request.target_collection))


def migrate_rag_vectors(request: RagMigrationRequest, current_user: UserPublic) -> LearningJob:
    plan = plan_qdrant_migration(request.profile_id, request.target_collection)
    previous_active = repository.get_active_rag_embedding_profile()
    target_profile = plan["target_profile"]
    if request.activate_profile and target_profile.get("id") != (previous_active or {}).get("id"):
        repository.activate_rag_embedding_profile(str(target_profile["id"]))
    try:
        result = repository.rebuild_all_document_chunks(
            collection_name=plan["target_collection"],
            recreate_collection=request.recreate_collection,
        )
    except Exception:
        if previous_active:
            repository.activate_rag_embedding_profile(previous_active["id"])
        raise
    index_result = result.get("index_result", {})
    learning_index_result = result.get("learning_index_result", {})
    if (
        index_result.get("state") == "fallback"
        or learning_index_result.get("state") == "fallback"
    ):
        if previous_active:
            repository.activate_rag_embedding_profile(previous_active["id"])
        raise ValueError(
            str(
                index_result.get("error")
                or learning_index_result.get("error")
                or "RAG migration failed during vector indexing"
            )
        )
    job = record_learning_job(
        "rag_migration",
        current_user,
        input_refs={
            "profile_id": request.profile_id,
            "target_collection": plan["target_collection"],
            "recreate_collection": request.recreate_collection,
            "activate_profile": request.activate_profile,
            "notes": request.notes,
        },
        output_refs={
            "plan": plan,
            "result": result,
            "vector_store": vector_store_status(),
        },
        status="completed",
    )
    return LearningJob(**job)


def prepare_peft_artifacts(job: dict[str, Any]) -> dict[str, Any]:
    input_refs = job.get("input_refs") or {}
    dataset_id = str(input_refs.get("dataset_id") or "")
    model_version_id = str(input_refs.get("model_version_id") or "")
    prompt_version_id = str(input_refs.get("prompt_version_id") or "")
    adapter_name = str(input_refs.get("adapter_name") or f"maintenance-wizard-{job['id'].lower()}")
    base_model = input_refs.get("base_model") or "qwen2.5-7b-instruct"
    training_config = input_refs.get("training_config") if isinstance(input_refs.get("training_config"), dict) else {}

    _validate_dataset_model_prompt(dataset_id, model_version_id, prompt_version_id)
    snapshot = repository.get_learning_dataset_snapshot(dataset_id)
    model = _model_version(model_version_id)
    prompt = _prompt_version(prompt_version_id)
    if not snapshot or not model or not prompt:
        raise ValueError("Learning dataset, model, or prompt version was not found")

    artifact_dir = _job_artifact_dir(job["id"])
    dataset_path = artifact_dir / "dataset.jsonl"
    manifest_path = artifact_dir / "training_manifest.json"
    dataset_path.write_text(snapshot["jsonl_content"], encoding="utf-8")
    manifest = {
        "schema_version": "1",
        "job_id": job["id"],
        "job_type": job["job_type"],
        "adapter_name": adapter_name,
        "base_model": base_model,
        "training_status": "prepared_for_external_peft_trainer",
        "dataset": {
            "id": snapshot["id"],
            "name": snapshot["name"],
            "example_count": snapshot["example_count"],
            "approved_only": snapshot["approved_only"],
        },
        "model_version": {
            "id": model["id"],
            "provider": model["provider"],
            "model_name": model["model_name"],
            "base_model": model["base_model"],
            "adapter_path": model.get("adapter_path"),
            "status": model["status"],
        },
        "prompt_version": {
            "id": prompt["id"],
            "assistant": prompt["assistant"],
            "version": prompt["version"],
            "status": prompt["status"],
        },
        "training_config": training_config,
        "recommended_open_source_tools": [
            "Hugging Face PEFT",
            "TRL SFTTrainer",
            "bitsandbytes or llama.cpp-compatible quantized training path",
            "MLflow or equivalent experiment tracking before adapter promotion",
        ],
        "promotion_gate": "Register a candidate adapter only after training artifacts exist and evaluation passes.",
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    dataset_artifact = _register_file_artifact(
        job_id=job["id"],
        artifact_type="peft_dataset_jsonl",
        path=dataset_path,
        metadata={"dataset_id": dataset_id, "example_count": snapshot["example_count"]},
    )
    manifest_artifact = _register_file_artifact(
        job_id=job["id"],
        artifact_type="peft_training_manifest",
        path=manifest_path,
        metadata={
            "dataset_id": dataset_id,
            "model_version_id": model_version_id,
            "prompt_version_id": prompt_version_id,
            "adapter_name": adapter_name,
            "base_model": base_model,
        },
    )
    repository.update_learning_job_status(
        job["id"],
        "running",
        output_refs={
            **(job.get("output_refs") or {}),
            "execution_mode": "prepared_artifacts",
            "training_status": "dataset_artifacts_prepared",
            "artifact_dir": str(artifact_dir),
            "dataset_artifact_id": dataset_artifact["id"],
            "manifest_artifact_id": manifest_artifact["id"],
        },
    )
    trainer_output = _run_external_peft_trainer(
        job=job,
        artifact_dir=artifact_dir,
        dataset_path=dataset_path,
        manifest_path=manifest_path,
        adapter_name=adapter_name,
        base_model=base_model,
        source_model=model,
    )
    return {
        "execution_mode": trainer_output.get("trainer_mode", "prepared_artifacts"),
        "training_status": trainer_output.get("training_status", "awaiting_external_peft_trainer"),
        "artifact_dir": str(artifact_dir),
        "artifacts": [dataset_artifact, manifest_artifact, *trainer_output.get("artifacts", [])],
        **{key: value for key, value in trainer_output.items() if key not in {"artifacts", "training_status"}},
    }


def _run_external_peft_trainer(
    *,
    job: dict[str, Any],
    artifact_dir: Path,
    dataset_path: Path,
    manifest_path: Path,
    adapter_name: str,
    base_model: str,
    source_model: dict[str, Any],
) -> dict[str, Any]:
    settings = get_settings()
    command = str(getattr(settings, "learning_peft_trainer_command", "") or "").strip()
    if not command:
        return {
            "trainer_mode": "prepared_artifacts",
            "training_status": "awaiting_external_peft_trainer",
        }

    command_args = shlex.split(command)
    if not command_args:
        raise ValueError("LEARNING_PEFT_TRAINER_COMMAND did not contain an executable")

    output_root = getattr(settings, "learning_peft_output_dir", None)
    output_dir = (_safe_output_root(output_root) / _safe_name(job["id"])) if output_root else artifact_dir / "adapter_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    timeout_seconds = int(getattr(settings, "learning_peft_trainer_timeout_seconds", 900) or 900)
    trainer_started_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    current_job = repository.get_learning_job(job["id"]) or job
    repository.update_learning_job_status(
        job["id"],
        "running",
        output_refs={
            **(current_job.get("output_refs") or {}),
            "execution_mode": "external_command",
            "trainer_mode": "external_command",
            "training_status": "trainer_running",
            "adapter_output_dir": str(output_dir),
            "trainer_started_at": trainer_started_at,
            "trainer_timeout_seconds": timeout_seconds,
        },
    )
    env = {
        **_peft_env_overrides(),
        **os.environ,
        "MW_PEFT_JOB_ID": job["id"],
        "MW_PEFT_DATASET_PATH": str(dataset_path),
        "MW_PEFT_MANIFEST_PATH": str(manifest_path),
        "MW_PEFT_OUTPUT_DIR": str(output_dir),
        "MW_PEFT_ADAPTER_NAME": adapter_name,
        "MW_PEFT_BASE_MODEL": base_model,
    }
    try:
        completed = subprocess.run(
            command_args,
            cwd=str(Path(__file__).resolve().parents[3]),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"External PEFT trainer timed out after {timeout_seconds} seconds") from exc

    log_path = artifact_dir / "trainer_output.log"
    log_path.write_text(
        "\n".join(
            [
                f"started_at={trainer_started_at}",
                f"completed_at={datetime.utcnow().isoformat(timespec='seconds')}Z",
                f"return_code={completed.returncode}",
                "",
                "[stdout]",
                completed.stdout or "",
                "",
                "[stderr]",
                completed.stderr or "",
            ]
        ),
        encoding="utf-8",
    )
    log_artifact = _register_file_artifact(
        job_id=job["id"],
        artifact_type="peft_training_log",
        path=log_path,
        metadata={"adapter_name": adapter_name, "return_code": completed.returncode},
    )
    if completed.returncode != 0:
        raise RuntimeError(f"External PEFT trainer failed with exit code {completed.returncode}")

    adapter_manifest_path = output_dir / "adapter_manifest.json"
    adapter_manifest = _read_adapter_manifest(adapter_manifest_path)
    registered_model = repository.save_learning_model_version(
        {
            "provider": adapter_manifest.get("provider") or source_model["provider"],
            "model_name": adapter_manifest.get("model_name") or f"{adapter_name}-trained",
            "base_model": adapter_manifest.get("base_model") or base_model,
            "adapter_path": adapter_manifest.get("adapter_path") or str(output_dir),
            "status": "candidate",
            "notes": adapter_manifest.get("notes")
            or f"Candidate adapter generated by external PEFT trainer for job {job['id']}.",
        }
    )
    registry_path = artifact_dir / "adapter_registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "job_id": job["id"],
                "adapter_name": adapter_name,
                "trainer_command_configured": True,
                "output_dir": str(output_dir),
                "adapter_manifest": adapter_manifest,
                "registered_model_version": registered_model,
                "registered_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    registry_artifact = _register_file_artifact(
        job_id=job["id"],
        artifact_type="peft_adapter_registry",
        path=registry_path,
        metadata={"model_version_id": registered_model["id"], "adapter_name": adapter_name},
    )
    output_refs: dict[str, Any] = {
        "trainer_mode": "external_command",
        "training_status": "adapter_candidate_registered",
        "trainer_return_code": completed.returncode,
        "adapter_output_dir": str(output_dir),
        "registered_model_version_id": registered_model["id"],
        "artifacts": [log_artifact, registry_artifact],
    }
    manifest_artifact = _register_file_artifact(
        job_id=job["id"],
        artifact_type="peft_adapter_manifest",
        path=adapter_manifest_path,
        metadata={"model_version_id": registered_model["id"], "adapter_name": adapter_name},
    )
    output_refs["artifacts"].append(manifest_artifact)
    return output_refs


def _read_adapter_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError("External PEFT trainer completed without writing adapter_manifest.json")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"External PEFT trainer wrote invalid adapter_manifest.json: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("External PEFT trainer adapter_manifest.json must be a JSON object")
    if not str(payload.get("adapter_path") or "").strip():
        raise ValueError("External PEFT trainer adapter_manifest.json must include adapter_path")
    return payload


def _peft_env_overrides() -> dict[str, str]:
    return env_file_values_for(
        prefixes=(
            "MW_PEFT_",
            "HF_",
            "HF_HUB_",
            "TRANSFORMERS_",
            "TOKENIZERS_",
            "ACCELERATE_",
            "WANDB_",
        )
    )


def _safe_output_root(path: Any) -> Path:
    root = Path(path)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_name(value: str) -> str:
    return "".join(character for character in value if character.isalnum() or character in {"-", "_"}) or "learning-job"


def _validate_dataset_model_prompt(dataset_id: str, model_version_id: str, prompt_version_id: str) -> None:
    if not repository.get_learning_dataset_snapshot(dataset_id):
        raise ValueError("Learning dataset not found")
    model_ids = {model["id"] for model in repository.list_learning_model_versions()}
    if model_version_id not in model_ids:
        raise ValueError("Learning adapter version not found")
    prompt_ids = {prompt["id"] for prompt in repository.list_learning_prompt_versions()}
    if prompt_version_id not in prompt_ids:
        raise ValueError("Learning prompt version not found")


def _model_version(model_version_id: str) -> Optional[dict[str, Any]]:
    return next(
        (model for model in repository.list_learning_model_versions() if model["id"] == model_version_id),
        None,
    )


def _prompt_version(prompt_version_id: str) -> Optional[dict[str, Any]]:
    return next(
        (prompt for prompt in repository.list_learning_prompt_versions() if prompt["id"] == prompt_version_id),
        None,
    )


def _job_artifact_dir(job_id: str) -> Path:
    settings = get_settings()
    safe_job_id = "".join(character for character in job_id if character.isalnum() or character in {"-", "_"})
    path = settings.learning_artifact_dir / safe_job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _register_file_artifact(
    *,
    job_id: str,
    artifact_type: str,
    path: Path,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    stored = store_learning_artifact_file(
        job_id=job_id,
        artifact_type=artifact_type,
        path=path,
        content_hash=content_hash,
        metadata=metadata,
    )
    return repository.save_learning_artifact(
        {
            "job_id": job_id,
            "artifact_type": artifact_type,
            "uri": stored.uri,
            "content_hash": content_hash,
            "metadata": stored.metadata,
        }
    )


def _learning_subject(job_type: str) -> str:
    suffix = LEARNING_JOB_SUBJECTS.get(job_type)
    if not suffix:
        raise ValueError(f"Unsupported learning job type: {job_type}")
    return f"{get_settings().learning_nats_subject_prefix}.{suffix}"


async def _publish_learning_job(job: dict[str, Any]) -> None:
    import nats
    from nats.js.api import StreamConfig

    settings = get_settings()
    connect_kwargs: dict[str, Any] = {
        "servers": [settings.nats_url],
        "max_reconnect_attempts": settings.nats_max_reconnect_attempts,
        "reconnect_time_wait": settings.nats_reconnect_time_wait_seconds,
    }
    if settings.nats_auth_token:
        connect_kwargs["token"] = settings.nats_auth_token
    if settings.nats_credentials_path:
        connect_kwargs["user_credentials"] = str(settings.nats_credentials_path)
    if settings.nats_tls_enabled:
        connect_kwargs["tls"] = ssl.create_default_context()

    nc = await nats.connect(**connect_kwargs)
    try:
        js = nc.jetstream()
        subjects = learning_stream_subjects(settings.learning_nats_subject_prefix)
        stream_config = StreamConfig(name=settings.learning_nats_stream, subjects=subjects)
        try:
            await js.add_stream(config=stream_config)
        except Exception as exc:
            if "already" in str(exc).lower():
                await js.update_stream(config=stream_config)
            else:
                raise
        await js.publish(job["subject"], json.dumps(_job_message(job)).encode("utf-8"))
    finally:
        await nc.close()


def _job_message(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "job_id": job["id"],
        "job_type": job["job_type"],
        "requested_by": job.get("requested_by"),
        "correlation_id": job["correlation_id"],
        "created_at": job.get("created_at") or datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "input_refs": job.get("input_refs") or {},
        "retry_count": job.get("retry_count") or 0,
    }


def set_example_approval(example_id: str, approved: bool) -> Optional[dict[str, Any]]:
    example = repository.set_learning_example_approval(example_id, approved)
    if example:
        sync_learning_examples_index([example], min_judge_score=TRAINING_WORTHY_SCORE)
    return example


def rejudge_learning_example(example_id: str) -> Optional[dict[str, Any]]:
    example = repository.get_learning_example(example_id)
    if not example:
        return None
    judgement = judge_learning_example(example)
    updated = repository.update_learning_example_judgement(
        example_id,
        judgement.score,
        judgement.label,
        judgement.rationale,
        judgement.provider,
        judgement.used_live_provider,
    )
    if updated:
        sync_learning_examples_index([updated], min_judge_score=TRAINING_WORTHY_SCORE)
    return updated


def judge_learning_example(example: dict[str, Any]) -> LearningJudgeResult:
    prompt = _judge_prompt(example)
    return configured_llm_client().complete_model(
        prompt,
        LearningJudgeResult,
        _judge_system_prompt(),
        lambda provider, reason: _fallback_judge(example, provider, reason),
    )


def _examples_from_feedback() -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for feedback in repository.list_feedback():
        status = str(feedback.get("status") or "").lower()
        equipment_id = feedback.get("equipment_id")
        instruction = "Improve future maintenance recommendations from human feedback."
        input_text = "\n".join(
            [
                f"Recommendation ID: {feedback['recommendation_id']}",
                f"Equipment: {equipment_id or 'unknown'}",
                f"Feedback status: {status}",
                f"Corrected diagnosis: {feedback.get('corrected_diagnosis') or 'not provided'}",
                f"Actual root cause: {feedback.get('actual_root_cause') or 'not provided'}",
                f"Notes: {feedback.get('notes') or 'not provided'}",
            ]
        )
        expected = "\n".join(
            part
            for part in [
                feedback.get("actual_root_cause") and f"Root cause: {feedback['actual_root_cause']}",
                feedback.get("action_taken") and f"Action: {feedback['action_taken']}",
                feedback.get("outcome") and f"Outcome: {feedback['outcome']}",
            ]
            if part
        ) or feedback.get("notes") or "Human feedback recorded."
        examples.append(
            _upsert_judged_example(
                {
                    "source_type": "feedback",
                    "source_id": str(feedback["id"]),
                    "equipment_id": equipment_id,
                    "instruction": instruction,
                    "input_text": _clip(input_text),
                    "expected_output": _clip(expected),
                    "metadata": {
                        "recommendation_id": feedback["recommendation_id"],
                        "status": status,
                    },
                    "approved": _approval_for("feedback", str(feedback["id"]), status in APPROVED_FEEDBACK_STATUSES),
                }
            )
        )
    return examples


def _examples_from_labels() -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for label in repository.list_maintenance_labels():
        input_text = "\n".join(
            [
                f"Source: {label['source_type']} {label['source_id']}",
                f"Equipment: {label.get('equipment_id') or 'unknown'}",
                f"Failure mode: {label['failure_mode']}",
                f"Component: {label['component']}",
                f"Signals: {', '.join(label.get('signal_hints') or []) or 'not provided'}",
            ]
        )
        expected = "\n".join(
            [
                f"Root cause: {label['root_cause']}",
                f"Action class: {label['action_class']}",
                f"Outcome: {label['outcome_status']}",
            ]
        )
        examples.append(
            _upsert_judged_example(
                {
                    "source_type": "maintenance_label",
                    "source_id": str(label["id"]),
                    "equipment_id": label.get("equipment_id"),
                    "instruction": "Map maintenance evidence to failure mode, component, root cause, action class, and outcome.",
                    "input_text": _clip(input_text),
                    "expected_output": _clip(expected),
                    "metadata": {
                        "source_type": label["source_type"],
                        "source_id": label["source_id"],
                        "provider": label.get("provider"),
                    },
                    "approved": _approval_for("maintenance_label", str(label["id"]), bool(label.get("usable_for_training"))),
                }
            )
        )
    return examples


def _examples_from_work_orders() -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for work_order in repository.list_work_orders():
        if work_order["status"] not in {"COMP", "CLOSE"} or not work_order.get("completion_summary"):
            continue
        input_text = "\n".join(
            [
                f"Work order: {work_order['id']}",
                f"Equipment: {work_order['equipment_id']}",
                f"Title: {work_order['title']}",
                f"Description: {work_order['description']}",
                f"Recommended action: {work_order['recommended_action']}",
                f"Problem code: {work_order['problem_code']}",
            ]
        )
        expected = "\n".join(
            [
                f"Completion summary: {work_order['completion_summary']}",
                f"Final status: {work_order['status']}",
                f"Follow-up required: {'yes' if work_order['follow_up_required'] else 'no'}",
            ]
        )
        examples.append(
            _upsert_judged_example(
                {
                    "source_type": "work_order_completion",
                    "source_id": work_order["id"],
                    "equipment_id": work_order["equipment_id"],
                    "work_order_id": work_order["id"],
                    "instruction": "Learn what good completion guidance and follow-up recommendations look like.",
                    "input_text": _clip(input_text),
                    "expected_output": _clip(expected),
                    "metadata": {
                        "status": work_order["status"],
                        "priority": work_order["priority"],
                    },
                    "approved": _approval_for("work_order_completion", work_order["id"], True),
                }
            )
        )
    return examples


def _examples_from_rca_cases() -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for case in repository.list_rca_cases(status="closed", limit=1000):
        closure = case.get("closure_review") or {}
        if not closure.get("accepted_for_learning"):
            continue
        input_text = "\n".join(
            [
                f"RCA case: {case['id']}",
                f"Equipment: {case['equipment_id']}",
                f"Work order: {case.get('work_order_id') or 'none'}",
                f"Problem: {case['problem_statement']}",
                f"Symptoms: {'; '.join(case.get('symptoms') or []) or 'not recorded'}",
                f"Probable cause: {case.get('probable_cause') or 'not recorded'}",
                f"Missing checks: {'; '.join(case.get('missing_checks') or []) or 'none'}",
            ]
        )
        expected = "\n".join(
            part
            for part in [
                closure.get("final_root_cause") and f"Root cause: {closure['final_root_cause']}",
                closure.get("recurrence_prevention") and f"Prevention: {closure['recurrence_prevention']}",
                closure.get("lessons_learned") and f"Lessons: {closure['lessons_learned']}",
            ]
            if part
        ) or case.get("morpheus_summary") or case.get("probable_cause") or "RCA closure accepted."
        examples.append(
            _upsert_judged_example(
                {
                    "source_type": "rca_case",
                    "source_id": case["id"],
                    "equipment_id": case["equipment_id"],
                    "work_order_id": case.get("work_order_id"),
                    "instruction": "Use accepted RCA closure to improve root-cause hypotheses and corrective actions.",
                    "input_text": _clip(input_text),
                    "expected_output": _clip(expected),
                    "metadata": {
                        "status": case["status"],
                        "confidence": case.get("confidence"),
                        "accepted_for_learning": True,
                    },
                    "approved": _approval_for("rca_case", case["id"], True),
                }
            )
        )
    return examples


def _examples_from_documents() -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for document in repository.list_documents():
        examples.append(
            _upsert_judged_example(
                {
                    "source_type": "document",
                    "source_id": document["id"],
                    "equipment_id": document.get("equipment_id"),
                    "instruction": "Use maintenance documents as grounding context for future recommendations.",
                    "input_text": _clip(f"{document['title']}\n\n{document['content']}"),
                    "expected_output": _clip(document["content"][:900]),
                    "metadata": {
                        "title": document["title"],
                        "source_type": document["source_type"],
                    },
                    "approved": _approval_for("document", document["id"], False),
                }
            )
        )
    return examples


def _examples_from_approved_interactions() -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for interaction in repository.list_learning_interactions(approved_only=True, limit=1000):
        examples.append(
            _upsert_judged_example(
                {
                    "source_type": "assistant_interaction",
                    "source_id": interaction["id"],
                    "equipment_id": interaction.get("equipment_id"),
                    "work_order_id": interaction.get("work_order_id"),
                    "instruction": f"Respond as {interaction['assistant']} for {interaction['interaction_type']}.",
                    "input_text": _clip(interaction["prompt"]),
                    "expected_output": _clip(interaction["response"]),
                    "metadata": {
                        "assistant": interaction["assistant"],
                        "provider": interaction["provider"],
                        "user_role": interaction.get("user_role"),
                    },
                    "approved": _approval_for("assistant_interaction", interaction["id"], True),
                }
            )
        )
    return examples


def _example_to_jsonl_line(example: dict[str, Any]) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "You are a steel-plant maintenance assistant. Ground recommendations in "
                "approved maintenance history, work-order outcomes, feedback, documents, and role-safe actions."
            ),
        },
        {
            "role": "user",
            "content": f"{example['instruction']}\n\n{example['input_text']}",
        },
        {"role": "assistant", "content": example["expected_output"]},
    ]
    return json.dumps(
        {
            "messages": messages,
            "metadata": {
                "example_id": example["id"],
                "source_type": example["source_type"],
                "source_id": example["source_id"],
                "equipment_id": example.get("equipment_id"),
                "work_order_id": example.get("work_order_id"),
                "judge_score": example.get("judge_score"),
                "judge_label": example.get("judge_label"),
                **(example.get("metadata") or {}),
            },
        },
        separators=(",", ":"),
    )


def _jsonl_records(content: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in content.splitlines():
        if not line.strip():
            continue
        try:
            decoded = json.loads(line)
        except ValueError:
            continue
        if isinstance(decoded, dict):
            records.append(decoded)
    return records


def _evaluation_metrics(records: list[dict[str, Any]], snapshot: dict[str, Any]) -> dict[str, Any]:
    judge_scores: list[float] = []
    labels: list[str] = []
    source_types: set[str] = set()
    asset_ids: set[str] = set()
    assistant_lengths: list[int] = []
    for record in records:
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        try:
            judge_scores.append(float(metadata.get("judge_score") or 0))
        except (TypeError, ValueError):
            judge_scores.append(0)
        labels.append(str(metadata.get("judge_label") or "not_scored"))
        if metadata.get("source_type"):
            source_types.add(str(metadata["source_type"]))
        if metadata.get("equipment_id"):
            asset_ids.add(str(metadata["equipment_id"]))
        messages = record.get("messages") if isinstance(record.get("messages"), list) else []
        assistant_text = " ".join(str(message.get("content") or "") for message in messages if message.get("role") == "assistant")
        assistant_lengths.append(len(assistant_text))

    example_count = len(records)
    average_score = sum(judge_scores) / example_count if example_count else 0
    minimum_score = min(judge_scores) if judge_scores else 0
    training_worthy_ratio = labels.count("training_worthy") / example_count if example_count else 0
    source_coverage_score = min(1.0, len(source_types) / 4)
    asset_coverage_score = min(1.0, len(asset_ids) / 3)
    quality_score = (
        (0.5 * average_score)
        + (0.2 * minimum_score)
        + (0.15 * training_worthy_ratio)
        + (0.1 * source_coverage_score)
        + (0.05 * asset_coverage_score)
    )
    return {
        "example_count": example_count,
        "snapshot_example_count": int(snapshot.get("example_count") or 0),
        "approved_only": bool(snapshot.get("approved_only")),
        "average_judge_score": round(average_score, 3),
        "minimum_judge_score": round(minimum_score, 3),
        "training_worthy_ratio": round(training_worthy_ratio, 3),
        "source_type_coverage": len(source_types),
        "asset_coverage": len(asset_ids),
        "average_assistant_output_chars": round(sum(assistant_lengths) / example_count, 1) if example_count else 0,
        "quality_score": round(quality_score, 3),
    }


def _clip(value: str) -> str:
    value = value.strip()
    if len(value) <= MAX_EXAMPLE_TEXT_CHARS:
        return value
    return f"{value[:MAX_EXAMPLE_TEXT_CHARS - 15].rstrip()}\n[truncated]"


def _approval_for(source_type: str, source_id: str, default: bool) -> bool:
    existing = repository.get_learning_example_by_source(source_type, source_id)
    if existing is None:
        return default
    return bool(existing.get("approved"))


def _upsert_judged_example(payload: dict[str, Any]) -> dict[str, Any]:
    return repository.upsert_learning_example(_with_judgement(payload))


def _with_judgement(payload: dict[str, Any]) -> dict[str, Any]:
    existing = repository.get_learning_example_by_source(payload["source_type"], payload["source_id"])
    if existing and existing.get("judge_label") != "not_scored":
        score = float(existing.get("judge_score") or 0)
        label = existing.get("judge_label") or "not_scored"
        rationale = existing.get("judge_rationale")
        provider = existing.get("judge_provider") or "not_scored"
        used_live_provider = bool(existing.get("judge_used_live_provider"))
    else:
        judgement = judge_learning_example(payload)
        score = judgement.score
        label = judgement.label
        rationale = judgement.rationale
        provider = judgement.provider
        used_live_provider = judgement.used_live_provider

    next_payload = {
        **payload,
        "judge_score": score,
        "judge_label": label,
        "judge_rationale": rationale,
        "judge_provider": provider,
        "judge_used_live_provider": used_live_provider,
    }
    if existing is None and payload.get("approved") and score < TRAINING_WORTHY_SCORE:
        next_payload["approved"] = False
    return next_payload


def _judge_prompt(example: dict[str, Any]) -> str:
    metadata = json.dumps(example.get("metadata") or {}, separators=(",", ":"))
    return "\n".join(
        [
            "Score whether this maintenance example is worthy for RAG reuse and PEFT tuning.",
            f"Source type: {example.get('source_type')}",
            f"Equipment: {example.get('equipment_id') or 'company-wide'}",
            f"Work order: {example.get('work_order_id') or 'none'}",
            f"Instruction: {example.get('instruction')}",
            "Input:",
            str(example.get("input_text") or "")[:1200],
            "Expected output:",
            str(example.get("expected_output") or "")[:1200],
            f"Metadata: {metadata[:800]}",
        ]
    )


def _judge_system_prompt() -> str:
    return (
        "You are an LLM-as-a-Judge for a steel-plant maintenance training pipeline. "
        "Return only JSON matching LearningJudgeResult. Score 0.0 to 1.0. "
        "A training_worthy example must be specific, grounded in maintenance evidence or outcome data, "
        "role-safe, operationally useful, and free of obvious hallucination or unsafe advice. "
        "Use label training_worthy for score >= 0.65, review for 0.45 to 0.64, and reject below 0.45. "
        "Reject examples that are generic, contradictory, unactionable, unsafe, secret-bearing, or lack enough context."
    )


def _fallback_judge(example: dict[str, Any], provider: str, reason: str) -> LearningJudgeResult:
    source_type = str(example.get("source_type") or "")
    input_text = str(example.get("input_text") or "")
    expected = str(example.get("expected_output") or "")
    combined = f"{input_text}\n{expected}".lower()
    score_by_source = {
        "feedback": 0.72,
        "maintenance_label": 0.7,
        "work_order_completion": 0.78,
        "assistant_interaction": 0.58,
        "document": 0.5,
    }
    score = score_by_source.get(source_type, 0.45)
    strengths: list[str] = []
    risks: list[str] = []
    if example.get("equipment_id"):
        score += 0.05
        strengths.append("Tied to a specific asset.")
    if any(term in combined for term in ("root cause", "action", "outcome", "completion summary")):
        score += 0.08
        strengths.append("Contains outcome or action structure.")
    if any(term in combined for term in ("lockout", "safety", "ppe", "isolate")):
        score += 0.03
        strengths.append("Includes safety-aware context.")
    if len(expected.strip()) < 40:
        score -= 0.18
        risks.append("Expected output is too short for robust tuning.")
    if "not provided" in combined:
        score -= 0.08
        risks.append("Some fields are missing.")
    if source_type == "document":
        risks.append("Document snippets need human approval before tuning export.")
    score = max(0.0, min(1.0, score))
    if score >= TRAINING_WORTHY_SCORE:
        label = "training_worthy"
    elif score >= 0.45:
        label = "review"
    else:
        label = "reject"
    rationale = (
        f"Deterministic judge fallback used because {reason}. "
        f"Source={source_type}; score reflects specificity, outcome evidence, and safety context."
    )
    return LearningJudgeResult(
        score=round(score, 2),
        label=label,
        rationale=rationale,
        strengths=strengths,
        risks=risks,
        used_live_provider=False,
        provider=provider,
    )
