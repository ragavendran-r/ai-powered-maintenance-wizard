from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import httpx

from app.core.config import get_settings
from app.data import repository


@dataclass(frozen=True)
class AdapterDeploymentResult:
    deployment_id: str
    model_version_id: str
    runtime_provider: str
    serving_provider: str
    served_model_name: str
    base_url: Optional[str]
    artifact_uri: Optional[str]
    artifact_hash: Optional[str]
    status: str
    health_status: str
    health_checked_at: str
    metadata: dict[str, Any]


def execute_adapter_deployment(job: dict[str, Any]) -> dict[str, Any]:
    input_refs = job.get("input_refs") or {}
    model_version_id = str(input_refs.get("model_version_id") or "").strip()
    model = repository.get_learning_model_version(model_version_id)
    if not model:
        raise ValueError("Learning model version not found for adapter deployment")
    if model.get("status") == "active":
        raise ValueError("Active models cannot be redeployed through a candidate deployment job")

    settings = get_settings()
    runtime_provider = str(
        input_refs.get("runtime_provider")
        or settings.learning_runtime_deployer_default
        or "manual"
    ).strip().lower()
    serving_provider = _serving_provider(runtime_provider, model)
    served_model_name = str(input_refs.get("served_model_name") or model.get("model_name") or "").strip()
    if not served_model_name:
        raise ValueError("Adapter deployment requires a served_model_name or model_name")

    base_url = str(input_refs.get("base_url") or _default_base_url(serving_provider, settings) or "").strip() or None
    artifact_uri = str(input_refs.get("artifact_uri") or model.get("adapter_path") or "").strip() or None
    artifact_hash = str(input_refs.get("artifact_hash") or "").strip() or None
    metadata = {
        "notes": input_refs.get("notes"),
        "requested_by": job.get("requested_by"),
        "runtime_provider": runtime_provider,
        "probe": "manual" if runtime_provider == "manual" else "chat_completion",
    }

    try:
        health_status, probe_metadata = _probe_runtime(
            runtime_provider=runtime_provider,
            serving_provider=serving_provider,
            served_model_name=served_model_name,
            base_url=base_url,
            timeout_seconds=settings.learning_runtime_deployment_timeout_seconds,
        )
    except Exception as exc:
        failed = _save_deployment(
            job=job,
            model=model,
            runtime_provider=runtime_provider,
            serving_provider=serving_provider,
            served_model_name=served_model_name,
            base_url=base_url,
            artifact_uri=artifact_uri,
            artifact_hash=artifact_hash,
            status="failed",
            health_status="failed",
            metadata=metadata,
            error=str(exc),
        )
        raise RuntimeError(f"Adapter runtime deployment failed: {exc}; deployment_id={failed['id']}") from exc

    deployment = _save_deployment(
        job=job,
        model=model,
        runtime_provider=runtime_provider,
        serving_provider=serving_provider,
        served_model_name=served_model_name,
        base_url=base_url,
        artifact_uri=artifact_uri,
        artifact_hash=artifact_hash,
        status="verified",
        health_status=health_status,
        metadata={**metadata, **probe_metadata},
        error=None,
    )
    return AdapterDeploymentResult(
        deployment_id=deployment["id"],
        model_version_id=deployment["model_version_id"],
        runtime_provider=deployment["runtime_provider"],
        serving_provider=deployment["serving_provider"],
        served_model_name=deployment["served_model_name"],
        base_url=deployment.get("base_url"),
        artifact_uri=deployment.get("artifact_uri"),
        artifact_hash=deployment.get("artifact_hash"),
        status=deployment["status"],
        health_status=deployment["health_status"],
        health_checked_at=deployment["health_checked_at"],
        metadata=deployment["metadata"],
    ).__dict__


def _save_deployment(
    *,
    job: dict[str, Any],
    model: dict[str, Any],
    runtime_provider: str,
    serving_provider: str,
    served_model_name: str,
    base_url: Optional[str],
    artifact_uri: Optional[str],
    artifact_hash: Optional[str],
    status: str,
    health_status: str,
    metadata: dict[str, Any],
    error: Optional[str],
) -> dict[str, Any]:
    return repository.save_learning_model_deployment(
        {
            "model_version_id": model["id"],
            "job_id": job["id"],
            "runtime_provider": runtime_provider,
            "serving_provider": serving_provider,
            "served_model_name": served_model_name,
            "base_url": base_url,
            "artifact_uri": artifact_uri,
            "artifact_hash": artifact_hash,
            "status": status,
            "health_status": health_status,
            "health_checked_at": _utc_now(),
            "metadata": metadata,
            "error": error,
        }
    )


def _probe_runtime(
    *,
    runtime_provider: str,
    serving_provider: str,
    served_model_name: str,
    base_url: Optional[str],
    timeout_seconds: float,
) -> tuple[str, dict[str, Any]]:
    if runtime_provider == "manual":
        return "manual_verified", {"message": "Manual deployment record accepted; external runtime must keep this served model loaded."}
    if serving_provider == "openai":
        return _probe_openai_compatible(served_model_name, base_url, timeout_seconds)
    if serving_provider == "ollama":
        return _probe_ollama(served_model_name, base_url, timeout_seconds)
    raise ValueError(f"Unsupported runtime provider: {runtime_provider}")


def _probe_openai_compatible(
    served_model_name: str,
    base_url: Optional[str],
    timeout_seconds: float,
) -> tuple[str, dict[str, Any]]:
    if not base_url:
        raise ValueError("OpenAI-compatible deployment requires base_url")
    settings = get_settings()
    headers = {"Content-Type": "application/json"}
    if settings.openai_api_key:
        headers["Authorization"] = f"Bearer {settings.openai_api_key}"
    response = httpx.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers=headers,
        json={
            "model": served_model_name,
            "messages": [
                {"role": "system", "content": "Return the single word READY."},
                {"role": "user", "content": "adapter deployment smoke test"},
            ],
            "temperature": 0,
            "max_tokens": 8,
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    return "healthy", {"probe_status_code": response.status_code, "probe_provider": "openai_compatible"}


def _probe_ollama(
    served_model_name: str,
    base_url: Optional[str],
    timeout_seconds: float,
) -> tuple[str, dict[str, Any]]:
    if not base_url:
        raise ValueError("Ollama deployment requires base_url")
    response = httpx.post(
        f"{base_url.rstrip('/')}/api/chat",
        json={
            "model": served_model_name,
            "messages": [
                {"role": "system", "content": "Return the single word READY."},
                {"role": "user", "content": "adapter deployment smoke test"},
            ],
            "stream": False,
            "options": {"num_predict": 8},
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    return "healthy", {"probe_status_code": response.status_code, "probe_provider": "ollama"}


def _serving_provider(runtime_provider: str, model: dict[str, Any]) -> str:
    if runtime_provider in {"ollama"}:
        return "ollama"
    if runtime_provider in {"openai", "openai_compatible", "lmstudio", "lm_studio", "vllm"}:
        return "openai"
    if runtime_provider == "manual":
        return str(model.get("provider") or "openai")
    return str(model.get("provider") or "openai")


def _default_base_url(serving_provider: str, settings: Any) -> Optional[str]:
    if serving_provider == "openai":
        return settings.openai_base_url
    if serving_provider == "ollama":
        return settings.ollama_base_url
    return None


def _utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"
