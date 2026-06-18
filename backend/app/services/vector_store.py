from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.core.config import get_settings
from app.services.embeddings import EmbeddingProfile, current_embedding_profile, embedding_profile_id, supported_embedding_provider
from app.services.vector_index import decode_embedding, embed_text


RAG_KIND_DOCUMENT_CHUNK = "document_chunk"
RAG_KIND_LEARNING_EXAMPLE = "learning_example"
RAG_KIND_PLANT_RECORD = "plant_record"


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
    if settings is not None:
        provider = settings.rag_embedding_provider
        model = settings.rag_embedding_model
        version = settings.rag_embedding_version
        dimensions = int(settings.rag_embedding_dimensions)
        distance = settings.rag_embedding_distance
        profile = EmbeddingProfile(
            id=embedding_profile_id(provider, model, version, dimensions, distance),
            provider=provider,
            model=model,
            version=version,
            dimensions=dimensions,
            distance=distance,
            status="settings",
        )
    else:
        profile = current_embedding_profile()
    profile = {
        "id": profile.id,
        "provider": profile.provider,
        "model": profile.model,
        "version": profile.version,
        "dimensions": profile.dimensions,
        "configured_dimensions": profile.dimensions,
        "distance": profile.distance,
        "status": profile.status,
        "state": "ready",
    }
    if not supported_embedding_provider(profile["provider"]):
        profile["state"] = "unsupported_provider_fallback"
        profile["warning"] = (
            f"Embedding provider {profile['provider']} requires an external embedding worker or OpenAI-compatible "
            "embedding endpoint before Qdrant indexing can use it."
        )
    elif settings is not None and profile["provider"] == "deterministic_hash" and profile["dimensions"] != 64:
        profile["state"] = "dimension_mismatch"
        profile["warning"] = (
            f"Configured dimensions {profile['dimensions']} do not match the deterministic hash embedding dimension 64."
        )
    return profile


def vector_store_status() -> dict[str, Any]:
    settings = get_settings()
    store = configured_vector_store_name()
    active_profile = current_embedding_profile()
    embedding_profile = embedding_profile_status()
    status = {
        "store": store,
        "enabled": store == "qdrant",
        "collection": settings.rag_qdrant_collection,
        "collection_alias": settings.rag_qdrant_collection_alias,
        "url": settings.rag_qdrant_url,
        "embedding_profile": embedding_profile,
        "points_count": None,
        "collection_vector_size": None,
        "collection_distance": None,
        "migration_reasons": [],
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
            distance = _collection_distance(collection)
            status["collection_vector_size"] = vector_size
            status["collection_distance"] = distance
            if vector_size is not None and vector_size != active_profile.dimensions:
                status["migration_required"] = True
                status["migration_reasons"].append(
                    f"Collection vector size {vector_size} does not match active profile dimensions {active_profile.dimensions}."
                )
            if distance and distance.lower() != active_profile.distance.lower():
                status["migration_required"] = True
                status["migration_reasons"].append(
                    f"Collection distance {distance} does not match active profile distance {active_profile.distance}."
                )
            status["state"] = "ready"
    except Exception as exc:
        status["state"] = "unavailable"
        status["error"] = str(exc)
    return status


def index_document_chunks(
    chunks: list[dict[str, Any]],
    *,
    collection_name: Optional[str] = None,
    recreate_collection: bool = False,
) -> dict[str, Any]:
    settings = get_settings()
    collection = collection_name or settings.rag_qdrant_collection
    profile = current_embedding_profile()
    if configured_vector_store_name() != "qdrant" or not chunks:
        return {
            "store": configured_vector_store_name(),
            "collection": collection,
            "embedding_profile_id": profile.id,
            "indexed": 0,
            "state": "skipped",
        }
    try:
        _ensure_qdrant_collection(collection, profile, recreate_collection=recreate_collection)
        points = [_chunk_to_point(chunk) for chunk in chunks]
        with _client() as client:
            response = client.put(
                f"/collections/{collection}/points",
                params={"wait": "true"},
                json={"points": points},
            )
        response.raise_for_status()
        return {
            "store": "qdrant",
            "collection": collection,
            "embedding_profile_id": profile.id,
            "indexed": len(points),
            "state": "indexed",
        }
    except Exception as exc:
        return {
            "store": "qdrant",
            "collection": collection,
            "embedding_profile_id": profile.id,
            "indexed": 0,
            "state": "fallback",
            "error": str(exc),
        }


def sync_learning_examples_index(
    examples: list[dict[str, Any]],
    *,
    collection_name: Optional[str] = None,
    min_judge_score: float = 0.65,
) -> dict[str, Any]:
    settings = get_settings()
    collection = collection_name or settings.rag_qdrant_collection
    profile = current_embedding_profile()
    eligible = [
        _learning_example_to_point(example, profile)
        for example in examples
        if _indexable_learning_example(example, min_judge_score)
    ]
    stale_point_ids = [
        _learning_example_point_id(example["id"], profile)
        for example in examples
        if not _indexable_learning_example(example, min_judge_score)
    ]
    if configured_vector_store_name() != "qdrant":
        return {
            "store": configured_vector_store_name(),
            "collection": collection,
            "embedding_profile_id": profile.id,
            "eligible": len(eligible),
            "indexed": 0,
            "deleted": 0,
            "state": "skipped",
        }
    try:
        _ensure_qdrant_collection(collection, profile)
        if eligible:
            with _client() as client:
                response = client.put(
                    f"/collections/{collection}/points",
                    params={"wait": "true"},
                    json={"points": eligible},
                )
            response.raise_for_status()
        if stale_point_ids:
            _delete_points(collection, stale_point_ids)
        return {
            "store": "qdrant",
            "collection": collection,
            "embedding_profile_id": profile.id,
            "eligible": len(eligible),
            "indexed": len(eligible),
            "deleted": len(stale_point_ids),
            "state": "synced",
        }
    except Exception as exc:
        return {
            "store": "qdrant",
            "collection": collection,
            "embedding_profile_id": profile.id,
            "eligible": len(eligible),
            "indexed": 0,
            "deleted": 0,
            "state": "fallback",
            "error": str(exc),
        }


def sync_plant_records_index(
    records: list[dict[str, Any]],
    *,
    collection_name: Optional[str] = None,
) -> dict[str, Any]:
    settings = get_settings()
    collection = collection_name or settings.rag_qdrant_collection
    profile = current_embedding_profile()
    points = [_plant_record_to_point(record, profile) for record in records if record.get("id") and record.get("content")]
    if configured_vector_store_name() != "qdrant":
        return {
            "store": configured_vector_store_name(),
            "collection": collection,
            "embedding_profile_id": profile.id,
            "indexed": 0,
            "state": "skipped",
        }
    try:
        _ensure_qdrant_collection(collection, profile)
        if points:
            with _client() as client:
                response = client.put(
                    f"/collections/{collection}/points",
                    params={"wait": "true"},
                    json={"points": points},
                )
            response.raise_for_status()
        return {
            "store": "qdrant",
            "collection": collection,
            "embedding_profile_id": profile.id,
            "indexed": len(points),
            "state": "synced",
        }
    except Exception as exc:
        return {
            "store": "qdrant",
            "collection": collection,
            "embedding_profile_id": profile.id,
            "indexed": 0,
            "state": "fallback",
            "error": str(exc),
        }


def delete_plant_records_index(
    source_ids: list[str],
    *,
    collection_name: Optional[str] = None,
) -> dict[str, Any]:
    settings = get_settings()
    collection = collection_name or settings.rag_qdrant_collection
    profile = current_embedding_profile()
    point_ids = [_plant_record_point_id(source_id, profile) for source_id in source_ids if source_id]
    if configured_vector_store_name() != "qdrant" or not point_ids:
        return {
            "store": configured_vector_store_name(),
            "collection": collection,
            "embedding_profile_id": profile.id,
            "deleted": 0,
            "state": "skipped",
        }
    try:
        _ensure_qdrant_collection(collection, profile)
        _delete_points(collection, point_ids)
        return {
            "store": "qdrant",
            "collection": collection,
            "embedding_profile_id": profile.id,
            "deleted": len(point_ids),
            "state": "deleted",
        }
    except Exception as exc:
        return {
            "store": "qdrant",
            "collection": collection,
            "embedding_profile_id": profile.id,
            "deleted": 0,
            "state": "fallback",
            "error": str(exc),
        }


def search_document_chunks(query: str, equipment_id: Optional[str], limit: int) -> list[VectorStoreHit]:
    if configured_vector_store_name() != "qdrant":
        return []
    profile = current_embedding_profile()
    try:
        _ensure_qdrant_collection(get_settings().rag_qdrant_collection, profile)
        candidate_limit = max(limit * 4, limit, 1)
        body = _search_body(query, profile, candidate_limit)
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
        rag_kind = payload.get("rag_kind")
        if rag_kind not in (None, "", RAG_KIND_DOCUMENT_CHUNK):
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


def search_plant_records(query: str, equipment_id: Optional[str], limit: int) -> list[VectorStoreHit]:
    if configured_vector_store_name() != "qdrant":
        return []
    profile = current_embedding_profile()
    try:
        _ensure_qdrant_collection(get_settings().rag_qdrant_collection, profile)
        candidate_limit = max(limit * 4, limit, 1)
        body = _search_body(query, profile, candidate_limit, rag_kind=RAG_KIND_PLANT_RECORD)
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
        if payload.get("rag_kind") != RAG_KIND_PLANT_RECORD:
            continue
        source_id = str(payload.get("source_id") or "")
        if not source_id:
            continue
        hit_equipment_id = payload.get("equipment_id")
        if equipment_id and hit_equipment_id not in (equipment_id, None, ""):
            continue
        hits.append(
            VectorStoreHit(
                source_id=source_id,
                title=str(payload.get("title") or "Plant record"),
                content=str(payload.get("content") or ""),
                source_type=str(payload.get("source_type") or RAG_KIND_PLANT_RECORD),
                equipment_id=hit_equipment_id,
                score=float(result.get("score") or 0),
            )
        )
        if len(hits) >= limit:
            break
    return hits


def search_learning_examples(query: str, equipment_id: Optional[str], limit: int) -> list[VectorStoreHit]:
    if configured_vector_store_name() != "qdrant":
        return []
    profile = current_embedding_profile()
    try:
        _ensure_qdrant_collection(get_settings().rag_qdrant_collection, profile)
        candidate_limit = max(limit * 4, limit, 1)
        body = _search_body(query, profile, candidate_limit, rag_kind=RAG_KIND_LEARNING_EXAMPLE)
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
        if payload.get("rag_kind") != RAG_KIND_LEARNING_EXAMPLE:
            continue
        source_id = str(payload.get("source_id") or "")
        if not source_id:
            continue
        hit_equipment_id = payload.get("equipment_id")
        if equipment_id and hit_equipment_id not in (equipment_id, None, ""):
            continue
        hits.append(
            VectorStoreHit(
                source_id=source_id,
                title=str(payload.get("title") or "Approved learning example"),
                content=str(payload.get("content") or ""),
                source_type=RAG_KIND_LEARNING_EXAMPLE,
                equipment_id=hit_equipment_id,
                score=float(result.get("score") or 0),
            )
        )
        if len(hits) >= limit:
            break
    return hits


def plan_qdrant_migration(profile_id: Optional[str] = None, target_collection: Optional[str] = None) -> dict[str, Any]:
    from app.data import repository

    active_profile = current_embedding_profile()
    target_profile = active_profile
    if profile_id:
        stored_profile = repository.get_rag_embedding_profile(profile_id)
        if not stored_profile:
            raise ValueError(f"RAG embedding profile {profile_id} was not found")
        target_profile = EmbeddingProfile(
            id=stored_profile["id"],
            provider=stored_profile["provider"],
            model=stored_profile["model"],
            version=stored_profile["version"],
            dimensions=int(stored_profile["dimensions"]),
            distance=stored_profile["distance"],
            status=stored_profile["status"],
            notes=stored_profile.get("notes"),
            metadata=stored_profile.get("metadata"),
        )
    if not supported_embedding_provider(target_profile.provider):
        raise ValueError(f"Embedding provider {target_profile.provider} is not supported by this runtime")
    status = vector_store_status()
    collection = target_collection or _default_target_collection(target_profile)
    reasons = list(status.get("migration_reasons") or [])
    if target_profile.id != active_profile.id:
        reasons.append(f"Selected profile {target_profile.id} differs from active profile {active_profile.id}.")
    if not reasons and status.get("state") == "missing_collection":
        reasons.append("Qdrant collection is missing.")
    if not reasons:
        reasons.append("Reindex current profile without collection migration.")
    return {
        "dry_run": True,
        "store": configured_vector_store_name(),
        "source_collection": get_settings().rag_qdrant_collection,
        "target_collection": collection,
        "active_profile": _profile_payload(active_profile),
        "target_profile": _profile_payload(target_profile),
        "migration_required": bool(status.get("migration_required") or target_profile.id != active_profile.id),
        "will_activate_profile": target_profile.id != active_profile.id,
        "will_recreate_collection": collection == get_settings().rag_qdrant_collection,
        "reasons": reasons,
        "status": status,
    }


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


def _ensure_qdrant_collection(
    collection_name: str,
    profile: EmbeddingProfile,
    *,
    recreate_collection: bool = False,
) -> None:
    with _client() as client:
        if recreate_collection:
            delete_response = client.delete(f"/collections/{collection_name}")
            if delete_response.status_code not in (200, 202, 404):
                delete_response.raise_for_status()
        response = client.get(f"/collections/{collection_name}")
        if response.status_code != 404:
            response.raise_for_status()
            collection = response.json().get("result") or {}
            vector_size = _collection_vector_size(collection)
            distance = _collection_distance(collection)
            if vector_size is not None and vector_size != profile.dimensions:
                raise ValueError(
                    f"Qdrant collection {collection_name} has vector size {vector_size}; profile {profile.id} requires {profile.dimensions}."
                )
            if distance and distance.lower() != profile.distance.lower():
                raise ValueError(
                    f"Qdrant collection {collection_name} has distance {distance}; profile {profile.id} requires {profile.distance}."
                )
            return
        create_response = client.put(
            f"/collections/{collection_name}",
            json={
                "vectors": {
                    "size": profile.dimensions,
                    "distance": profile.distance,
                }
            },
        )
        create_response.raise_for_status()


def _search_body(
    query: str,
    profile: EmbeddingProfile,
    limit: int,
    *,
    rag_kind: Optional[str] = None,
) -> dict[str, Any]:
    must = [
        {
            "key": "embedding_profile_id",
            "match": {"value": profile.id},
        }
    ]
    if rag_kind:
        must.append({"key": "rag_kind", "match": {"value": rag_kind}})
    return {
        "vector": embed_text(query, profile),
        "limit": limit,
        "with_payload": True,
        "filter": {"must": must},
    }


def _chunk_to_point(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, chunk["id"])),
        "vector": decode_embedding(chunk["embedding"]),
        "payload": {
            "rag_kind": RAG_KIND_DOCUMENT_CHUNK,
            "source_id": chunk["id"],
            "document_id": chunk["document_id"],
            "chunk_index": chunk["chunk_index"],
            "source_type": chunk["source_type"],
            "equipment_id": chunk.get("equipment_id"),
            "title": chunk["title"],
            "content": chunk["content"],
            "embedding_profile_id": chunk.get("embedding_profile_id"),
            "embedding_provider": chunk.get("embedding_provider"),
            "embedding_model": chunk.get("embedding_model"),
            "embedding_version": chunk.get("embedding_version"),
            "embedding_dimensions": chunk.get("embedding_dimensions"),
            "embedding_distance": chunk.get("embedding_distance"),
        },
    }


def _indexable_learning_example(example: dict[str, Any], min_judge_score: float) -> bool:
    return (
        bool(example.get("approved"))
        and float(example.get("judge_score") or 0) >= min_judge_score
    )


def _learning_example_point_id(example_id: str, profile: EmbeddingProfile) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"learning-example:{profile.id}:{example_id}"))


def _learning_example_to_point(example: dict[str, Any], profile: EmbeddingProfile) -> dict[str, Any]:
    text = "\n".join(
        [
            str(example.get("instruction") or ""),
            str(example.get("input_text") or ""),
            str(example.get("expected_output") or ""),
        ]
    )
    source_type = str(example.get("source_type") or "learning")
    return {
        "id": _learning_example_point_id(str(example["id"]), profile),
        "vector": embed_text(text, profile),
        "payload": {
            "rag_kind": RAG_KIND_LEARNING_EXAMPLE,
            "source_id": example["id"],
            "learning_source_type": source_type,
            "learning_source_id": example.get("source_id"),
            "work_order_id": example.get("work_order_id"),
            "source_type": RAG_KIND_LEARNING_EXAMPLE,
            "equipment_id": example.get("equipment_id"),
            "title": f"Approved learning: {source_type}",
            "content": example.get("expected_output") or "",
            "instruction": example.get("instruction"),
            "judge_score": example.get("judge_score"),
            "judge_label": example.get("judge_label"),
            "embedding_profile_id": profile.id,
            "embedding_provider": profile.provider,
            "embedding_model": profile.model,
            "embedding_version": profile.version,
            "embedding_dimensions": profile.dimensions,
            "embedding_distance": profile.distance,
        },
    }


def _plant_record_to_point(record: dict[str, Any], profile: EmbeddingProfile) -> dict[str, Any]:
    text = str(record.get("content") or "")
    source_id = str(record["id"])
    return {
        "id": _plant_record_point_id(source_id, profile),
        "vector": embed_text(text, profile),
        "payload": {
            "rag_kind": RAG_KIND_PLANT_RECORD,
            "source_id": source_id,
            "source_type": record.get("source_type") or RAG_KIND_PLANT_RECORD,
            "equipment_id": record.get("equipment_id"),
            "title": record.get("title") or "Plant record",
            "content": text,
            "timestamp": record.get("timestamp"),
            "embedding_profile_id": profile.id,
            "embedding_provider": profile.provider,
            "embedding_model": profile.model,
            "embedding_version": profile.version,
            "embedding_dimensions": profile.dimensions,
            "embedding_distance": profile.distance,
        },
    }


def _plant_record_point_id(source_id: str, profile: EmbeddingProfile) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"plant-record:{profile.id}:{source_id}"))


def _delete_points(collection: str, point_ids: list[str]) -> None:
    if not point_ids:
        return
    with _client() as client:
        response = client.post(
            f"/collections/{collection}/points/delete",
            params={"wait": "true"},
            json={"points": point_ids},
        )
    response.raise_for_status()


def _collection_vector_size(collection: dict[str, Any]) -> Optional[int]:
    vectors = (((collection.get("config") or {}).get("params") or {}).get("vectors") or {})
    if isinstance(vectors, dict) and "size" in vectors:
        return int(vectors["size"])
    if isinstance(vectors, dict):
        for value in vectors.values():
            if isinstance(value, dict) and "size" in value:
                return int(value["size"])
    return None


def _collection_distance(collection: dict[str, Any]) -> Optional[str]:
    vectors = (((collection.get("config") or {}).get("params") or {}).get("vectors") or {})
    if isinstance(vectors, dict) and "distance" in vectors:
        return str(vectors["distance"])
    if isinstance(vectors, dict):
        for value in vectors.values():
            if isinstance(value, dict) and "distance" in value:
                return str(value["distance"])
    return None


def _default_target_collection(profile: EmbeddingProfile) -> str:
    settings = get_settings()
    active_profile = current_embedding_profile()
    if profile.id == active_profile.id:
        return settings.rag_qdrant_collection
    return f"{settings.rag_qdrant_collection}_{profile.id.replace('-', '_')}"


def _profile_payload(profile: EmbeddingProfile) -> dict[str, Any]:
    return {
        "id": profile.id,
        "provider": profile.provider,
        "model": profile.model,
        "version": profile.version,
        "dimensions": profile.dimensions,
        "distance": profile.distance,
        "status": profile.status,
        "notes": profile.notes,
        "metadata": profile.metadata or {},
    }
