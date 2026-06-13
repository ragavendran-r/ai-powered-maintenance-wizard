from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class StoredArtifactRef:
    uri: str
    metadata: dict[str, Any]


def artifact_store_status(settings: Optional[Settings] = None) -> dict[str, Any]:
    settings = settings or get_settings()
    store = settings.learning_artifact_store.lower().strip()
    status = {
        "store": store or "filesystem",
        "local_dir": str(settings.learning_artifact_dir),
    }
    if store == "s3":
        status.update(
            {
                "bucket": settings.learning_artifact_s3_bucket,
                "prefix": settings.learning_artifact_s3_prefix,
                "endpoint_url": settings.learning_artifact_s3_endpoint_url,
                "region": settings.learning_artifact_s3_region,
                "state": "configured" if settings.learning_artifact_s3_bucket else "missing_bucket",
            }
        )
    else:
        status["state"] = "ready"
    return status


def store_learning_artifact_file(
    *,
    job_id: str,
    artifact_type: str,
    path: Path,
    content_hash: str,
    metadata: dict[str, Any],
    settings: Optional[Settings] = None,
) -> StoredArtifactRef:
    settings = settings or get_settings()
    backend = settings.learning_artifact_store.lower().strip()
    if backend in {"", "filesystem", "file", "local"}:
        return StoredArtifactRef(
            uri=str(path),
            metadata={
                **metadata,
                "storage_backend": "filesystem",
                "local_path": str(path),
                "content_hash_algorithm": "sha256",
            },
        )
    if backend == "s3":
        return _store_s3_artifact(
            job_id=job_id,
            artifact_type=artifact_type,
            path=path,
            content_hash=content_hash,
            metadata=metadata,
            settings=settings,
        )
    raise ValueError(f"Unsupported learning artifact store: {settings.learning_artifact_store}")


def _store_s3_artifact(
    *,
    job_id: str,
    artifact_type: str,
    path: Path,
    content_hash: str,
    metadata: dict[str, Any],
    settings: Settings,
) -> StoredArtifactRef:
    if not settings.learning_artifact_s3_bucket:
        raise ValueError("LEARNING_ARTIFACT_S3_BUCKET is required when LEARNING_ARTIFACT_STORE=s3")
    key = _artifact_object_key(settings.learning_artifact_s3_prefix, job_id, artifact_type, path.name)
    client = _s3_client(settings)
    client.upload_file(
        str(path),
        settings.learning_artifact_s3_bucket,
        key,
        ExtraArgs={
            "Metadata": {
                "job-id": job_id,
                "artifact-type": artifact_type,
                "sha256": content_hash,
            }
        },
    )
    return StoredArtifactRef(
        uri=f"s3://{settings.learning_artifact_s3_bucket}/{key}",
        metadata={
            **metadata,
            "storage_backend": "s3",
            "bucket": settings.learning_artifact_s3_bucket,
            "object_key": key,
            "endpoint_url": settings.learning_artifact_s3_endpoint_url,
            "region": settings.learning_artifact_s3_region,
            "local_path": str(path),
            "local_retained": True,
            "content_hash_algorithm": "sha256",
        },
    )


def _artifact_object_key(prefix: str, job_id: str, artifact_type: str, filename: str) -> str:
    safe_prefix = prefix.strip("/")
    safe_job_id = "".join(character for character in job_id if character.isalnum() or character in {"-", "_"})
    safe_artifact_type = "".join(character for character in artifact_type if character.isalnum() or character in {"-", "_"})
    parts = [part for part in [safe_prefix, safe_job_id, safe_artifact_type, filename] if part]
    return "/".join(parts)


def _s3_client(settings: Settings):
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 is required when LEARNING_ARTIFACT_STORE=s3") from exc
    return boto3.client(
        "s3",
        endpoint_url=settings.learning_artifact_s3_endpoint_url,
        region_name=settings.learning_artifact_s3_region,
    )
