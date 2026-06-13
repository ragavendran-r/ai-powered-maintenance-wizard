from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.core.config import get_settings


@dataclass(frozen=True)
class EmbeddingProfile:
    id: str
    provider: str
    model: str
    version: str
    dimensions: int
    distance: str
    status: str = "candidate"
    notes: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


def embedding_profile_id(
    provider: str,
    model: str,
    version: str,
    dimensions: int,
    distance: str,
) -> str:
    slug_source = f"{provider}:{model}:{version}:{dimensions}:{distance}".lower()
    digest = hashlib.sha256(slug_source.encode("utf-8")).hexdigest()[:12]
    return f"emb-{digest}"


def settings_embedding_profile() -> EmbeddingProfile:
    settings = get_settings()
    provider = settings.rag_embedding_provider.strip() or "deterministic_hash"
    model = settings.rag_embedding_model.strip() or "maintenance-hash-v1"
    version = settings.rag_embedding_version.strip() or "1"
    dimensions = int(settings.rag_embedding_dimensions)
    distance = settings.rag_embedding_distance.strip() or "Cosine"
    return EmbeddingProfile(
        id=embedding_profile_id(provider, model, version, dimensions, distance),
        provider=provider,
        model=model,
        version=version,
        dimensions=dimensions,
        distance=distance,
        status="active",
        notes="Environment-configured embedding profile.",
        metadata={"source": "settings"},
    )


def current_embedding_profile() -> EmbeddingProfile:
    try:
        from app.data.database import is_initializing_database

        if is_initializing_database():
            return settings_embedding_profile()
        from app.data import repository

        active = repository.get_active_rag_embedding_profile()
        if active:
            return _profile_from_record(active)
    except Exception:
        pass
    return settings_embedding_profile()


def supported_embedding_provider(provider: str) -> bool:
    return provider in {"deterministic_hash", "openai", "openai_compatible"}


def embed_text(text: str, profile: Optional[EmbeddingProfile] = None) -> list[float]:
    profile = profile or current_embedding_profile()
    if profile.provider == "deterministic_hash":
        return deterministic_hash_embedding(text, profile.dimensions)
    if profile.provider in {"openai", "openai_compatible"}:
        return _openai_compatible_embedding(text, profile)
    raise ValueError(f"Unsupported embedding provider: {profile.provider}")


def deterministic_hash_embedding(text: str, dimensions: int) -> list[float]:
    from app.services.vector_index import tokenize

    vector = [0.0] * dimensions
    for token in tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % dimensions
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[index] += sign
    norm = sum(value * value for value in vector) ** 0.5
    if norm == 0:
        return vector
    return [round(value / norm, 6) for value in vector]


def _openai_compatible_embedding(text: str, profile: EmbeddingProfile) -> list[float]:
    settings = get_settings()
    base_url = (settings.rag_embedding_base_url or settings.openai_base_url).rstrip("/")
    api_key = settings.rag_embedding_api_key or settings.openai_api_key
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload: dict[str, Any] = {
        "model": profile.model,
        "input": text,
    }
    if profile.dimensions:
        payload["dimensions"] = profile.dimensions
    with httpx.Client(base_url=base_url, timeout=settings.rag_embedding_timeout_seconds, headers=headers) as client:
        response = client.post("/embeddings", json=payload)
    response.raise_for_status()
    data = response.json()
    embedding = (((data.get("data") or [{}])[0] or {}).get("embedding") or [])
    vector = [float(value) for value in embedding]
    if len(vector) != profile.dimensions:
        raise ValueError(
            f"Embedding provider returned {len(vector)} dimensions for profile {profile.id}; expected {profile.dimensions}"
        )
    return vector


def _profile_from_record(record: dict[str, Any]) -> EmbeddingProfile:
    return EmbeddingProfile(
        id=record["id"],
        provider=record["provider"],
        model=record["model"],
        version=record["version"],
        dimensions=int(record["dimensions"]),
        distance=record["distance"],
        status=record.get("status") or "candidate",
        notes=record.get("notes"),
        metadata=record.get("metadata") if isinstance(record.get("metadata"), dict) else {},
    )
