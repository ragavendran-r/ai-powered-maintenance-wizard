from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.core.config import get_settings
from app.services.vector_index import VECTOR_DIMENSIONS, decode_embedding, embed_text


@dataclass
class VectorStoreHit:
    source_id: str
    title: str
    content: str
    source_type: str
    equipment_id: Optional[str]
    score: float


def configured_vector_store_name() -> str:
    return get_settings().rag_vector_store.strip().lower()


def embedding_profile_status(settings: Optional[Any] = None) -> dict[str, Any]:
    settings = settings or get_settings()
    provider = str(getattr(settings, "rag_embedding_provider", "deterministic_hash") or "deterministic_hash")
    configured_dimensions = int(getattr(settings, "rag_embedding_dimensions", VECTOR_DIMENSIONS) or VECTOR_DIMENSIONS)
    profile = {
        "provider": provider,
        "model": getattr(settings, "rag_embedding_model", "maintenance-hash-v1"),
        "version": getattr(settings, "rag_embedding_version", "1"),
        "dimensions": VECTOR_DIMENSIONS,
        "configured_dimensions": configured_dimensions,
        "distance": getattr(settings, "rag_embedding_distance", "Cosine"),
        "state": "ready",
    }
    if provider != "deterministic_hash":
        profile["state"] = "unsupported_provider_fallback"
        profile["warning"] = "Only deterministic_hash embeddings are implemented in-app; configure an external embedding worker before switching providers."
    elif configured_dimensions != VECTOR_DIMENSIONS:
        profile["state"] = "dimension_mismatch"
        profile["warning"] = f"Configured dimensions {configured_dimensions} do not match active dimensions {VECTOR_DIMENSIONS}."
    return profile


def vector_store_status() -> dict[str, Any]:
    settings = get_settings()
    store = configured_vector_store_name()
    embedding_profile = embedding_profile_status(settings)
    status = {
        "store": store,
        "enabled": store == "qdrant",
        "collection": settings.rag_qdrant_collection,
        "url": settings.rag_qdrant_url,
        "embedding_profile": embedding_profile,
        "points_count": None,
        "collection_vector_size": None,
        "migration_required": embedding_profile["state"] != "ready",
        "state": "fallback",
        "error": None,
    }
    if store != "qdrant":
        return status
    try:
        with _client() as client:
            response = client.get(f"/collections/{settings.rag_qdrant_collection}")
        if response.status_code == 404:
            status["state"] = "missing_collection"
        else:
            response.raise_for_status()
            collection = response.json().get("result") or {}
            status["points_count"] = collection.get("points_count")
            if status["points_count"] is None:
                status["points_count"] = collection.get("vectors_count")
            vector_size = _collection_vector_size(collection)
            status["collection_vector_size"] = vector_size
            if vector_size is not None and vector_size != VECTOR_DIMENSIONS:
                status["migration_required"] = True
            status["state"] = "ready"
    except Exception as exc:
        status["state"] = "unavailable"
        status["error"] = str(exc)
    return status


def index_document_chunks(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    if configured_vector_store_name() != "qdrant" or not chunks:
        return {
            "store": configured_vector_store_name(),
            "collection": get_settings().rag_qdrant_collection,
            "indexed": 0,
            "state": "skipped",
        }
    try:
        _ensure_qdrant_collection()
        points = [_chunk_to_point(chunk) for chunk in chunks]
        with _client() as client:
            response = client.put(
                f"/collections/{get_settings().rag_qdrant_collection}/points",
                params={"wait": "true"},
                json={"points": points},
            )
        response.raise_for_status()
        return {
            "store": "qdrant",
            "collection": get_settings().rag_qdrant_collection,
            "indexed": len(points),
            "state": "indexed",
        }
    except Exception as exc:
        return {
            "store": "qdrant",
            "collection": get_settings().rag_qdrant_collection,
            "indexed": 0,
            "state": "fallback",
            "error": str(exc),
        }


def search_document_chunks(query: str, equipment_id: Optional[str], limit: int) -> list[VectorStoreHit]:
    if configured_vector_store_name() != "qdrant":
        return []
    try:
        _ensure_qdrant_collection()
        candidate_limit = max(limit * 4, limit, 1)
        body: dict[str, Any] = {
            "vector": embed_text(query),
            "limit": candidate_limit,
            "with_payload": True,
        }
        with _client() as client:
            response = client.post(
                f"/collections/{get_settings().rag_qdrant_collection}/points/search",
                json=body,
            )
        response.raise_for_status()
        results = response.json().get("result", [])
    except Exception:
        return []
    hits: list[VectorStoreHit] = []
    for result in results:
        payload = result.get("payload") or {}
        source_id = str(payload.get("source_id") or "")
        if not source_id:
            continue
        hit_equipment_id = payload.get("equipment_id")
        if equipment_id and hit_equipment_id not in (equipment_id, None, ""):
            continue
        hits.append(
            VectorStoreHit(
                source_id=source_id,
                title=str(payload.get("title") or "Document chunk"),
                content=str(payload.get("content") or ""),
                source_type=str(payload.get("source_type") or "document"),
                equipment_id=hit_equipment_id,
                score=float(result.get("score") or 0),
            )
        )
        if len(hits) >= limit:
            break
    return hits


def _client() -> httpx.Client:
    settings = get_settings()
    headers = {}
    if settings.rag_qdrant_api_key:
        headers["api-key"] = settings.rag_qdrant_api_key
    return httpx.Client(
        base_url=settings.rag_qdrant_url.rstrip("/"),
        headers=headers,
        timeout=settings.rag_vector_timeout_seconds,
    )


def _ensure_qdrant_collection() -> None:
    settings = get_settings()
    with _client() as client:
        response = client.get(f"/collections/{settings.rag_qdrant_collection}")
        if response.status_code != 404:
            response.raise_for_status()
            return
        create_response = client.put(
            f"/collections/{settings.rag_qdrant_collection}",
            json={
                "vectors": {
                    "size": VECTOR_DIMENSIONS,
                    "distance": settings.rag_embedding_distance,
                }
            },
        )
        create_response.raise_for_status()


def _chunk_to_point(chunk: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, chunk["id"])),
        "vector": decode_embedding(chunk["embedding"]),
        "payload": {
            "source_id": chunk["id"],
            "document_id": chunk["document_id"],
            "chunk_index": chunk["chunk_index"],
            "source_type": chunk["source_type"],
            "equipment_id": chunk.get("equipment_id"),
            "title": chunk["title"],
            "content": chunk["content"],
            "embedding_provider": settings.rag_embedding_provider,
            "embedding_model": settings.rag_embedding_model,
            "embedding_version": settings.rag_embedding_version,
            "embedding_dimensions": VECTOR_DIMENSIONS,
        },
    }


def _collection_vector_size(collection: dict[str, Any]) -> Optional[int]:
    vectors = (((collection.get("config") or {}).get("params") or {}).get("vectors") or {})
    if isinstance(vectors, dict) and "size" in vectors:
        return int(vectors["size"])
    if isinstance(vectors, dict):
        for value in vectors.values():
            if isinstance(value, dict) and "size" in value:
                return int(value["size"])
    return None
