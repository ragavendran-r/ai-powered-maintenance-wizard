import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from dotenv import dotenv_values

from app.core.config import Settings, get_settings
from app.data import repository


FILESYSTEM_STORES = {"", "filesystem", "file", "local"}
RETENTION_DAYS_ENV = "LEARNING_ARTIFACT_RETENTION_DAYS"
CLEANUP_ENABLED_ENV = "LEARNING_ARTIFACT_CLEANUP_ENABLED"


@dataclass(frozen=True)
class StoredArtifactRef:
    uri: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ArtifactRetentionPolicy:
    retention_days: int
    cleanup_enabled: bool
    dry_run_default: bool
    errors: tuple[str, ...] = ()

    @property
    def enabled(self) -> bool:
        return self.retention_days > 0 and not self.errors

    @property
    def state(self) -> str:
        if self.errors:
            return "invalid_config"
        if not self.enabled:
            return "disabled"
        return "ready"

    def status_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "enabled": self.enabled,
            "retention_days": self.retention_days,
            "cleanup_enabled": self.cleanup_enabled,
            "dry_run_default": self.dry_run_default,
            "scope": "local_filesystem",
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class ExpiredFilesystemArtifact:
    path: str
    relative_path: str
    size_bytes: int
    modified_at: str
    age_days: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "modified_at": self.modified_at,
            "age_days": self.age_days,
        }


def artifact_store_status(settings: Optional[Settings] = None) -> dict[str, Any]:
    settings = settings or get_settings()
    store = settings.learning_artifact_store.lower().strip()
    retention_policy = learning_artifact_retention_policy(settings)
    status = {
        "store": store or "filesystem",
        "local_dir": str(settings.learning_artifact_dir),
        "retention": retention_policy.status_dict(),
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


def learning_artifact_retention_policy(settings: Optional[Settings] = None) -> ArtifactRetentionPolicy:
    settings = settings or get_settings()
    errors = []
    retention_days = 0
    cleanup_enabled = False

    retention_raw = _configured_value(
        settings,
        "learning_artifact_retention_days",
        RETENTION_DAYS_ENV,
        default="0",
    )
    cleanup_raw = _configured_value(
        settings,
        "learning_artifact_cleanup_enabled",
        CLEANUP_ENABLED_ENV,
        default="false",
    )

    try:
        retention_days = int(str(retention_raw).strip() or "0")
        if retention_days < 0:
            errors.append(f"{RETENTION_DAYS_ENV} must be greater than or equal to 0")
    except (TypeError, ValueError):
        errors.append(f"{RETENTION_DAYS_ENV} must be an integer number of days")

    try:
        cleanup_enabled = _parse_bool(cleanup_raw)
    except ValueError:
        errors.append(f"{CLEANUP_ENABLED_ENV} must be a boolean value")

    return ArtifactRetentionPolicy(
        retention_days=max(retention_days, 0),
        cleanup_enabled=cleanup_enabled,
        dry_run_default=True,
        errors=tuple(errors),
    )


def validate_learning_artifact_lifecycle_config(settings: Optional[Settings] = None) -> list[str]:
    return list(learning_artifact_retention_policy(settings).errors)


def find_expired_filesystem_artifacts(
    *,
    settings: Optional[Settings] = None,
    reference_time: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    policy = learning_artifact_retention_policy(settings)
    if policy.errors:
        raise ValueError(f"Invalid learning artifact lifecycle config: {'; '.join(policy.errors)}")
    if not policy.enabled:
        return []

    root = Path(settings.learning_artifact_dir)
    if not root.exists() or not root.is_dir():
        return []

    now = _utc(reference_time or datetime.now(timezone.utc))
    cutoff = now - timedelta(days=policy.retention_days)
    expired: list[ExpiredFilesystemArtifact] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        stat = path.stat()
        modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        if modified_at >= cutoff:
            continue
        expired.append(
            ExpiredFilesystemArtifact(
                path=str(path),
                relative_path=str(path.relative_to(root)),
                size_bytes=stat.st_size,
                modified_at=modified_at.isoformat(),
                age_days=max(0, (now - modified_at).days),
            )
        )
    return [candidate.as_dict() for candidate in expired]


def cleanup_expired_filesystem_artifacts(
    *,
    settings: Optional[Settings] = None,
    reference_time: Optional[datetime] = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    settings = settings or get_settings()
    policy = learning_artifact_retention_policy(settings)
    candidates = find_expired_filesystem_artifacts(settings=settings, reference_time=reference_time)
    deleted_paths: list[str] = []
    delete_requested = not dry_run
    deletion_allowed = policy.cleanup_enabled and delete_requested

    if deletion_allowed:
        root = Path(settings.learning_artifact_dir).resolve()
        for candidate in candidates:
            path = Path(candidate["path"]).resolve()
            if root not in path.parents:
                continue
            if path.is_symlink() or not path.is_file():
                continue
            path.unlink()
            deleted_paths.append(str(path))

    return {
        "dry_run": dry_run,
        "cleanup_enabled": policy.cleanup_enabled,
        "deletion_allowed": deletion_allowed,
        "expired_count": len(candidates),
        "deleted_count": len(deleted_paths),
        "deleted_paths": deleted_paths,
        "candidates": candidates,
    }


def cleanup_registered_learning_artifacts(
    *,
    settings: Optional[Settings] = None,
    reference_time: Optional[datetime] = None,
    dry_run: bool = True,
    limit: int = 1000,
) -> dict[str, Any]:
    settings = settings or get_settings()
    policy = learning_artifact_retention_policy(settings)
    store = settings.learning_artifact_store.lower().strip() or "filesystem"
    result = {
        "dry_run": dry_run,
        "cleanup_enabled": policy.cleanup_enabled,
        "deletion_allowed": False,
        "store": store,
        "retention": policy.status_dict(),
        "expired_count": 0,
        "protected_count": 0,
        "deleted_count": 0,
        "deleted_paths": [],
        "candidates": [],
        "protected": [],
        "errors": [],
    }
    if policy.errors:
        raise ValueError(f"Invalid learning artifact lifecycle config: {'; '.join(policy.errors)}")
    if store not in FILESYSTEM_STORES:
        result["errors"].append("Registered artifact cleanup is read-only for non-filesystem stores")
        return result
    if not policy.enabled:
        return result

    root = Path(settings.learning_artifact_dir).resolve()
    if not root.exists() or not root.is_dir():
        return result

    now = _utc(reference_time or datetime.now(timezone.utc))
    cutoff = now - timedelta(days=policy.retention_days)
    protected_refs = _protected_artifact_refs()
    artifacts = repository.list_learning_artifacts(limit=limit)
    candidates: list[dict[str, Any]] = []
    protected: list[dict[str, Any]] = []

    for artifact in artifacts:
        artifact_path = _artifact_path(artifact)
        if not artifact_path:
            continue
        path = artifact_path.resolve()
        if root not in path.parents or path.is_symlink() or not path.is_file():
            continue
        stat = path.stat()
        modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        if modified_at >= cutoff:
            continue
        entry = _artifact_cleanup_entry(
            artifact=artifact,
            root=root,
            path=path,
            stat=stat,
            modified_at=modified_at,
            now=now,
        )
        protected_reason = _artifact_protected_reason(artifact, protected_refs)
        if protected_reason:
            protected.append({**entry, "cleanup_eligible": False, "protected_reason": protected_reason})
        else:
            candidates.append({**entry, "cleanup_eligible": True})

    result["candidates"] = candidates
    result["protected"] = protected
    result["expired_count"] = len(candidates)
    result["protected_count"] = len(protected)
    delete_requested = not dry_run
    deletion_allowed = policy.cleanup_enabled and delete_requested
    result["deletion_allowed"] = deletion_allowed

    if deletion_allowed:
        deleted_paths: list[str] = []
        for candidate in candidates:
            path = (root / candidate["relative_path"]).resolve()
            if root not in path.parents or path.is_symlink() or not path.is_file():
                continue
            path.unlink()
            deleted_paths.append(candidate["relative_path"])
        result["deleted_paths"] = deleted_paths
        result["deleted_count"] = len(deleted_paths)

    return result


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
    if backend in FILESYSTEM_STORES:
        return StoredArtifactRef(
            uri=str(path),
            metadata={
                **metadata,
                "storage_backend": "filesystem",
                "local_path": str(path),
                "retention": learning_artifact_retention_policy(settings).status_dict(),
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
            "retention": learning_artifact_retention_policy(settings).status_dict(),
            "content_hash_algorithm": "sha256",
        },
    )


def _artifact_object_key(prefix: str, job_id: str, artifact_type: str, filename: str) -> str:
    safe_prefix = prefix.strip("/")
    safe_job_id = "".join(character for character in job_id if character.isalnum() or character in {"-", "_"})
    safe_artifact_type = "".join(character for character in artifact_type if character.isalnum() or character in {"-", "_"})
    parts = [part for part in [safe_prefix, safe_job_id, safe_artifact_type, filename] if part]
    return "/".join(parts)


def _artifact_path(artifact: dict[str, Any]) -> Optional[Path]:
    metadata = artifact.get("metadata") or {}
    storage_backend = str(metadata.get("storage_backend") or "").lower().strip()
    if storage_backend and storage_backend not in FILESYSTEM_STORES:
        return None
    local_path = metadata.get("local_path") or artifact.get("uri")
    if not local_path or str(local_path).startswith("s3://"):
        return None
    return Path(str(local_path))


def _artifact_cleanup_entry(
    *,
    artifact: dict[str, Any],
    root: Path,
    path: Path,
    stat: os.stat_result,
    modified_at: datetime,
    now: datetime,
) -> dict[str, Any]:
    return {
        "artifact_id": artifact["id"],
        "job_id": artifact["job_id"],
        "artifact_type": artifact["artifact_type"],
        "relative_path": str(path.relative_to(root)),
        "size_bytes": stat.st_size,
        "modified_at": modified_at.isoformat(),
        "age_days": max(0, (now - modified_at).days),
        "content_hash": artifact.get("content_hash"),
    }


def _protected_artifact_refs() -> dict[str, set[str]]:
    uris: set[str] = set()
    hashes: set[str] = set()
    promoted_model_ids = {
        promotion["model_version_id"]
        for promotion in repository.list_learning_model_promotions(limit=1000)
        if promotion.get("model_version_id")
    }
    for model in repository.list_learning_model_versions():
        adapter_path = model.get("adapter_path")
        if adapter_path and (model.get("status") in {"active", "candidate"} or model.get("id") in promoted_model_ids):
            uris.add(str(adapter_path))
    for deployment in repository.list_learning_model_deployments(limit=1000):
        if deployment.get("status") == "verified":
            if deployment.get("artifact_uri"):
                uris.add(str(deployment["artifact_uri"]))
            if deployment.get("artifact_hash"):
                hashes.add(str(deployment["artifact_hash"]))
    return {"uris": uris, "hashes": hashes}


def _artifact_protected_reason(artifact: dict[str, Any], protected_refs: dict[str, set[str]]) -> Optional[str]:
    metadata = artifact.get("metadata") or {}
    uris = {
        str(value)
        for value in {
            artifact.get("uri"),
            metadata.get("local_path"),
        }
        if value
    }
    if uris & protected_refs["uris"]:
        return "Referenced by an active/candidate/promoted model or verified deployment"
    content_hash = artifact.get("content_hash")
    if content_hash and str(content_hash) in protected_refs["hashes"]:
        return "Referenced by a verified runtime deployment hash"
    return None


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


def _configured_value(settings: Settings, attribute: str, env_name: str, *, default: str) -> Any:
    if hasattr(settings, attribute):
        value = getattr(settings, attribute)
        if value is not None:
            return value
    if env_name in os.environ:
        return os.environ[env_name]
    for env_file in _settings_env_files():
        value = dotenv_values(env_file).get(env_name)
        if value not in {None, ""}:
            return value
    return default


def _settings_env_files() -> list[Path]:
    env_files = Settings.model_config.get("env_file", ())
    if isinstance(env_files, (str, Path)):
        env_files = (env_files,)
    return [Path(env_file) for env_file in env_files if Path(env_file).exists()]


def _parse_bool(value: Any) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off", ""}:
        return False
    raise ValueError(value)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
