from typing import Any, Optional

import json
import sqlite3
from threading import Lock
import uuid

from app.core.security import hash_password
from app.data.database import connect, initialize_database
from app.services.vector_index import build_chunks_for_document
from app.services.vector_store import index_document_chunks, sync_learning_examples_index


_READY = False
_READY_LOCK = Lock()


def ensure_ready() -> None:
    global _READY
    if _READY:
        return
    with _READY_LOCK:
        if not _READY:
            initialize_database(seed=True)
            _READY = True


def list_equipment() -> list[dict[str, Any]]:
    return _fetch_all("SELECT * FROM equipment ORDER BY criticality DESC, name ASC")


def get_equipment(equipment_id: str) -> Optional[dict[str, Any]]:
    return _fetch_one("SELECT * FROM equipment WHERE id = ?", (equipment_id,))


def list_asset_profiles() -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT e.*, p.*
        FROM equipment e
        JOIN asset_profiles p ON p.equipment_id = e.id
        ORDER BY e.criticality DESC, e.name ASC
        """
    )


def get_asset_profile(equipment_id: str) -> Optional[dict[str, Any]]:
    return _fetch_one(
        """
        SELECT e.*, p.*
        FROM equipment e
        JOIN asset_profiles p ON p.equipment_id = e.id
        WHERE e.id = ?
        """,
        (equipment_id,),
    )


def list_asset_metric_snapshots(equipment_id: str) -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT * FROM asset_metric_snapshots
        WHERE equipment_id = ?
        ORDER BY sort_order ASC, label ASC
        """,
        (equipment_id,),
    )


def list_asset_recommendations(equipment_id: str) -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT * FROM asset_recommendations
        WHERE equipment_id = ?
        ORDER BY priority ASC, sort_order ASC
        """,
        (equipment_id,),
    )


def list_asset_subsystems(equipment_id: str) -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT * FROM asset_subsystems
        WHERE equipment_id = ?
        ORDER BY sort_order ASC, name ASC
        """,
        (equipment_id,),
    )


def list_asset_reliability_metrics(equipment_id: str) -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT * FROM asset_reliability_metrics
        WHERE equipment_id = ?
        ORDER BY sort_order ASC, metric_name ASC
        """,
        (equipment_id,),
    )


def list_alerts(equipment_id: Optional[str] = None) -> list[dict[str, Any]]:
    if equipment_id:
        return _fetch_all("SELECT * FROM alerts WHERE equipment_id = ? ORDER BY timestamp DESC", (equipment_id,))
    return _fetch_all("SELECT * FROM alerts ORDER BY timestamp DESC")


def list_spares(equipment_id: str) -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT * FROM spares
        WHERE equipment_id = ?
        ORDER BY available_qty ASC, lead_time_days DESC, criticality DESC
        """,
        (equipment_id,),
    )


def list_sensor_readings(equipment_id: Optional[str] = None, signal: Optional[str] = None) -> list[dict[str, Any]]:
    if equipment_id and signal:
        return _fetch_all(
            "SELECT * FROM sensor_readings WHERE equipment_id = ? AND signal = ? ORDER BY timestamp ASC",
            (equipment_id, signal),
        )
    if equipment_id:
        return _fetch_all("SELECT * FROM sensor_readings WHERE equipment_id = ? ORDER BY signal ASC, timestamp ASC", (equipment_id,))
    return _fetch_all("SELECT * FROM sensor_readings ORDER BY equipment_id ASC, signal ASC, timestamp ASC")


def list_maintenance_events(equipment_id: Optional[str] = None) -> list[dict[str, Any]]:
    if equipment_id:
        return _fetch_all("SELECT * FROM maintenance_events WHERE equipment_id = ? ORDER BY date DESC", (equipment_id,))
    return _fetch_all("SELECT * FROM maintenance_events ORDER BY date DESC")


def list_work_orders(
    equipment_id: Optional[str] = None,
    assigned_to: Optional[str] = None,
    follow_up_only: bool = False,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if equipment_id:
        clauses.append("equipment_id = ?")
        params.append(equipment_id)
    if assigned_to:
        clauses.append("assigned_to = ?")
        params.append(assigned_to)
    if follow_up_only:
        clauses.append("follow_up_required = 1")
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = _fetch_all(
        f"""
        SELECT * FROM work_orders
        {where_sql}
        ORDER BY priority ASC, due_date ASC, updated_at DESC
        """,
        tuple(params),
    )
    return [_decode_work_order(row, include_logs=False) for row in rows]


def get_work_order(work_order_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one("SELECT * FROM work_orders WHERE id = ?", (work_order_id,))
    if not row:
        return None
    return _decode_work_order(row, include_logs=True)


def create_work_order(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_ready()
    work_order_id = payload.get("id") or _next_work_order_id()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO work_orders (
                id,
                equipment_id,
                title,
                description,
                status,
                priority,
                work_type,
                failure_class,
                problem_code,
                classification,
                assigned_to,
                supervisor,
                due_date,
                recommended_action,
                follow_up_required,
                ai_summary,
                completion_summary,
                completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                work_order_id,
                payload["equipment_id"],
                payload["title"],
                payload["description"],
                payload.get("status") or "WAPPR",
                payload["priority"],
                payload.get("work_type") or "CM",
                payload.get("failure_class") or "MECH",
                payload.get("problem_code") or "INVESTIGATE",
                payload.get("classification") or "Corrective",
                payload.get("assigned_to") or "Maintenance Engineer",
                payload.get("supervisor") or "Maintenance Supervisor",
                payload["due_date"],
                payload.get("recommended_action") or "Inspect asset and update work log with findings.",
                1 if payload.get("follow_up_required") else 0,
                payload.get("ai_summary"),
                payload.get("completion_summary"),
                payload.get("completed_at"),
            ),
        )
        connection.execute(
            """
            INSERT INTO work_order_logs (work_order_id, author, entry_type, content)
            VALUES (?, ?, ?, ?)
            """,
            (
                work_order_id,
                "Maintenance Wizard",
                "created",
                payload.get("ai_summary") or "Work order created from maintenance operations dashboard.",
            ),
        )
    work_order = get_work_order(work_order_id)
    if not work_order:
        raise RuntimeError("Work order was not persisted")
    return work_order


def update_work_order(work_order_id: str, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    ensure_ready()
    existing = get_work_order(work_order_id)
    if not existing:
        return None
    fields: list[str] = []
    values: list[Any] = []
    for field in (
        "status",
        "priority",
        "assigned_to",
        "supervisor",
        "due_date",
        "recommended_action",
        "problem_code",
        "failure_class",
        "classification",
        "ai_summary",
        "completion_summary",
    ):
        if payload.get(field) is not None:
            fields.append(f"{field} = ?")
            values.append(payload[field])
    if payload.get("follow_up_required") is not None:
        fields.append("follow_up_required = ?")
        values.append(1 if payload["follow_up_required"] else 0)
    if payload.get("status") in {"COMP", "CLOSE"} and not existing.get("completed_at"):
        fields.append("completed_at = CURRENT_TIMESTAMP")
    if not fields:
        return existing
    fields.append("updated_at = CURRENT_TIMESTAMP")
    values.append(work_order_id)
    with connect() as connection:
        connection.execute(f"UPDATE work_orders SET {', '.join(fields)} WHERE id = ?", values)
    return get_work_order(work_order_id)


def add_work_order_log(work_order_id: str, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    ensure_ready()
    if not get_work_order(work_order_id):
        return None
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO work_order_logs (work_order_id, author, entry_type, content)
            VALUES (?, ?, ?, ?)
            """,
            (
                work_order_id,
                payload["author"],
                payload.get("entry_type") or "note",
                payload["content"],
            ),
        )
        connection.execute("UPDATE work_orders SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (work_order_id,))
    return get_work_order(work_order_id)


def list_documents(equipment_id: Optional[str] = None) -> list[dict[str, Any]]:
    if equipment_id:
        return _fetch_all(
            "SELECT * FROM documents WHERE equipment_id = ? OR equipment_id IS NULL ORDER BY source_type, title",
            (equipment_id,),
        )
    return _fetch_all("SELECT * FROM documents ORDER BY source_type, title")


def get_document(document_id: str) -> Optional[dict[str, Any]]:
    return _fetch_one("SELECT * FROM documents WHERE id = ?", (document_id,))


def list_document_chunks(equipment_id: Optional[str] = None, current_profile_only: bool = False) -> list[dict[str, Any]]:
    profile_id: Optional[str] = None
    if current_profile_only:
        from app.services.embeddings import current_embedding_profile

        profile_id = current_embedding_profile().id
    if equipment_id:
        if profile_id:
            return _fetch_all(
                """
                SELECT * FROM document_chunks
                WHERE (equipment_id = ? OR equipment_id IS NULL)
                  AND embedding_profile_id = ?
                ORDER BY source_type, title, chunk_index
                """,
                (equipment_id, profile_id),
            )
        return _fetch_all(
            """
            SELECT * FROM document_chunks
            WHERE equipment_id = ? OR equipment_id IS NULL
            ORDER BY source_type, title, chunk_index
            """,
            (equipment_id,),
        )
    if profile_id:
        return _fetch_all(
            """
            SELECT * FROM document_chunks
            WHERE embedding_profile_id = ?
            ORDER BY source_type, title, chunk_index
            """,
            (profile_id,),
        )
    return _fetch_all("SELECT * FROM document_chunks ORDER BY source_type, title, chunk_index")


def rebuild_all_document_chunks(
    *,
    collection_name: Optional[str] = None,
    recreate_collection: bool = False,
) -> dict[str, Any]:
    ensure_ready()
    with connect() as connection:
        documents = [dict(row) for row in connection.execute("SELECT * FROM documents ORDER BY source_type, title").fetchall()]
        connection.execute("DELETE FROM document_chunks")
        chunk_rows = upsert_document_chunks(connection, documents)
    index_result = index_document_chunks(
        chunk_rows,
        collection_name=collection_name,
        recreate_collection=recreate_collection,
    )
    learning_examples = list_learning_examples(limit=10000)
    learning_index_result = sync_learning_examples_index(
        learning_examples,
        collection_name=collection_name,
    )
    return {
        "document_count": len(documents),
        "chunk_count": len(chunk_rows),
        "index_result": index_result,
        "learning_example_count": len(learning_examples),
        "learning_index_result": learning_index_result,
    }


def add_documents(documents: list[dict[str, Any]]) -> int:
    ensure_ready()
    if not documents:
        return 0
    chunk_rows: list[dict[str, Any]] = []
    with connect() as connection:
        connection.executemany(
            """
            INSERT INTO documents (id, source_type, equipment_id, title, content)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                source_type=excluded.source_type,
                equipment_id=excluded.equipment_id,
                title=excluded.title,
                content=excluded.content
            """,
            [
                (
                    document["id"],
                    document["source_type"],
                    document.get("equipment_id"),
                    document["title"],
                    document["content"],
                )
                for document in documents
            ],
        )
        chunk_rows = upsert_document_chunks(connection, documents)
    index_document_chunks(chunk_rows)
    return len(documents)


def save_document_intelligence(payload: dict[str, Any]) -> None:
    ensure_ready()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO document_intelligence (
                document_id,
                summary,
                asset_ids,
                components,
                failure_modes,
                symptoms,
                safety_constraints,
                spares,
                thresholds,
                used_live_provider,
                provider
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_id) DO UPDATE SET
                summary=excluded.summary,
                asset_ids=excluded.asset_ids,
                components=excluded.components,
                failure_modes=excluded.failure_modes,
                symptoms=excluded.symptoms,
                safety_constraints=excluded.safety_constraints,
                spares=excluded.spares,
                thresholds=excluded.thresholds,
                used_live_provider=excluded.used_live_provider,
                provider=excluded.provider,
                created_at=CURRENT_TIMESTAMP
            """,
            (
                payload["document_id"],
                payload["summary"],
                _json_dump(payload.get("asset_ids", [])),
                _json_dump(payload.get("components", [])),
                _json_dump(payload.get("failure_modes", [])),
                _json_dump(payload.get("symptoms", [])),
                _json_dump(payload.get("safety_constraints", [])),
                _json_dump(payload.get("spares", [])),
                _json_dump(payload.get("thresholds", [])),
                1 if payload.get("used_live_provider") else 0,
                payload.get("provider") or "mock",
            ),
        )


def list_document_intelligence(equipment_id: Optional[str] = None) -> list[dict[str, Any]]:
    if equipment_id:
        rows = _fetch_all(
            """
            SELECT di.* FROM document_intelligence di
            JOIN documents d ON d.id = di.document_id
            WHERE d.equipment_id = ? OR d.equipment_id IS NULL
            ORDER BY di.created_at DESC
            """,
            (equipment_id,),
        )
    else:
        rows = _fetch_all("SELECT * FROM document_intelligence ORDER BY created_at DESC")
    return [_decode_document_intelligence(row) for row in rows]


def rebuild_document_chunks(connection: sqlite3.Connection) -> None:
    documents = [dict(row) for row in connection.execute("SELECT * FROM documents").fetchall()]
    connection.execute("DELETE FROM document_chunks")
    chunk_rows = upsert_document_chunks(connection, documents)
    index_document_chunks(chunk_rows)


def upsert_document_chunks(connection: sqlite3.Connection, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not documents:
        return []
    chunk_rows: list[dict[str, Any]] = []
    for document in documents:
        connection.execute("DELETE FROM document_chunks WHERE document_id = ?", (document["id"],))
        chunk_rows.extend(build_chunks_for_document(document))
    connection.executemany(
        """
        INSERT INTO document_chunks (
            id,
            document_id,
            chunk_index,
            source_type,
            equipment_id,
            title,
            content,
            embedding,
            embedding_profile_id,
            embedding_provider,
            embedding_model,
            embedding_version,
            embedding_dimensions,
            embedding_distance,
            embedded_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            document_id=excluded.document_id,
            chunk_index=excluded.chunk_index,
            source_type=excluded.source_type,
            equipment_id=excluded.equipment_id,
            title=excluded.title,
            content=excluded.content,
            embedding=excluded.embedding,
            embedding_profile_id=excluded.embedding_profile_id,
            embedding_provider=excluded.embedding_provider,
            embedding_model=excluded.embedding_model,
            embedding_version=excluded.embedding_version,
            embedding_dimensions=excluded.embedding_dimensions,
            embedding_distance=excluded.embedding_distance,
            embedded_at=CURRENT_TIMESTAMP
        """,
        [
            (
                chunk["id"],
                chunk["document_id"],
                chunk["chunk_index"],
                chunk["source_type"],
                chunk.get("equipment_id"),
                chunk["title"],
                chunk["content"],
                chunk["embedding"],
                chunk["embedding_profile_id"],
                chunk["embedding_provider"],
                chunk["embedding_model"],
                chunk["embedding_version"],
                chunk["embedding_dimensions"],
                chunk["embedding_distance"],
            )
            for chunk in chunk_rows
        ],
    )
    return chunk_rows


def add_records(payload: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    ensure_ready()
    table_columns = {
        "equipment": ["id", "name", "area", "process", "criticality", "status"],
        "alerts": ["id", "equipment_id", "timestamp", "signal", "value", "unit", "threshold", "severity", "message"],
        "spares": ["id", "equipment_id", "name", "available_qty", "lead_time_days", "criticality"],
        "sensor_readings": ["id", "equipment_id", "timestamp", "signal", "value", "unit", "threshold"],
        "maintenance_events": ["id", "equipment_id", "date", "issue", "root_cause", "action", "downtime_hours"],
        "work_orders": [
            "id",
            "equipment_id",
            "title",
            "description",
            "status",
            "priority",
            "work_type",
            "failure_class",
            "problem_code",
            "classification",
            "assigned_to",
            "supervisor",
            "due_date",
            "recommended_action",
            "follow_up_required",
            "ai_summary",
            "completion_summary",
            "completed_at",
        ],
    }
    counts: dict[str, int] = {}
    with connect() as connection:
        for table, columns in table_columns.items():
            rows = payload.get(table, [])
            if not rows:
                counts[table] = 0
                continue
            placeholders = ", ".join(["?"] * len(columns))
            update_sql = ", ".join(f"{column}=excluded.{column}" for column in columns if column != "id")
            connection.executemany(
                f"""
                INSERT INTO {table} ({", ".join(columns)})
                VALUES ({placeholders})
                ON CONFLICT(id) DO UPDATE SET {update_sql}
                """,
                [[row.get(column) for column in columns] for row in rows],
            )
            counts[table] = len(rows)
    return counts


def save_feedback(recommendation_id: str, feedback: dict[str, Any]) -> None:
    ensure_ready()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO feedback (
                recommendation_id,
                equipment_id,
                status,
                corrected_diagnosis,
                actual_root_cause,
                action_taken,
                outcome,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                recommendation_id,
                feedback.get("equipment_id"),
                feedback["status"],
                feedback.get("corrected_diagnosis"),
                feedback.get("actual_root_cause"),
                feedback.get("action_taken"),
                feedback.get("outcome"),
                feedback.get("notes"),
            ),
        )


def list_feedback(equipment_id: Optional[str] = None) -> list[dict[str, Any]]:
    if equipment_id:
        return _fetch_all(
            """
            SELECT * FROM feedback
            WHERE equipment_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (equipment_id,),
        )
    return _fetch_all("SELECT * FROM feedback ORDER BY created_at DESC, id DESC")


def save_maintenance_label(payload: dict[str, Any]) -> None:
    ensure_ready()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO maintenance_labels (
                source_type,
                source_id,
                equipment_id,
                failure_mode,
                component,
                root_cause,
                action_class,
                outcome_status,
                signal_hints,
                usable_for_training,
                used_live_provider,
                provider
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_type, source_id) DO UPDATE SET
                equipment_id=excluded.equipment_id,
                failure_mode=excluded.failure_mode,
                component=excluded.component,
                root_cause=excluded.root_cause,
                action_class=excluded.action_class,
                outcome_status=excluded.outcome_status,
                signal_hints=excluded.signal_hints,
                usable_for_training=excluded.usable_for_training,
                used_live_provider=excluded.used_live_provider,
                provider=excluded.provider,
                created_at=CURRENT_TIMESTAMP
            """,
            (
                payload["source_type"],
                payload["source_id"],
                payload.get("equipment_id"),
                payload["failure_mode"],
                payload["component"],
                payload["root_cause"],
                payload["action_class"],
                payload["outcome_status"],
                _json_dump(payload.get("signal_hints", [])),
                1 if payload.get("usable_for_training", True) else 0,
                1 if payload.get("used_live_provider") else 0,
                payload.get("provider") or "mock",
            ),
        )


def list_maintenance_labels(equipment_id: Optional[str] = None) -> list[dict[str, Any]]:
    if equipment_id:
        rows = _fetch_all(
            """
            SELECT * FROM maintenance_labels
            WHERE equipment_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (equipment_id,),
        )
    else:
        rows = _fetch_all("SELECT * FROM maintenance_labels ORDER BY created_at DESC, id DESC")
    return [_decode_maintenance_label(row) for row in rows]


def get_user_by_id(user_id: str) -> Optional[dict[str, Any]]:
    return _normalize_user(_fetch_one("SELECT * FROM users WHERE id = ?", (user_id,)))


def get_user_by_email(email: str) -> Optional[dict[str, Any]]:
    return _normalize_user(_fetch_one("SELECT * FROM users WHERE lower(email) = lower(?)", (email,)))


def list_users() -> list[dict[str, Any]]:
    return [
        _normalize_user(user) or user
        for user in _fetch_all("SELECT * FROM users ORDER BY role ASC, display_name ASC")
    ]


def create_user(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_ready()
    user_id = payload.get("id") or f"USER-{uuid.uuid4().hex[:12].upper()}"
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO users (
                id,
                email,
                display_name,
                role,
                password_hash,
                is_active
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                payload["email"].strip().lower(),
                payload["display_name"].strip(),
                payload["role"],
                hash_password(payload["password"]),
                1 if payload.get("is_active", True) else 0,
            ),
        )
    user = get_user_by_id(user_id)
    if not user:
        raise RuntimeError("User was not persisted")
    return user


def update_user(user_id: str, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    ensure_ready()
    existing = get_user_by_id(user_id)
    if not existing:
        return None
    fields: list[str] = []
    values: list[Any] = []
    if payload.get("display_name") is not None:
        fields.append("display_name = ?")
        values.append(payload["display_name"].strip())
    if payload.get("role") is not None:
        fields.append("role = ?")
        values.append(payload["role"])
    if payload.get("is_active") is not None:
        fields.append("is_active = ?")
        values.append(1 if payload["is_active"] else 0)
    if not fields:
        return existing
    fields.append("updated_at = CURRENT_TIMESTAMP")
    values.append(user_id)
    with connect() as connection:
        connection.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", values)
    return get_user_by_id(user_id)


def reset_user_password(user_id: str, password: str) -> Optional[dict[str, Any]]:
    ensure_ready()
    if not get_user_by_id(user_id):
        return None
    with connect() as connection:
        connection.execute(
            """
            UPDATE users
            SET password_hash = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (hash_password(password), user_id),
        )
    return get_user_by_id(user_id)


def record_user_login(user_id: str) -> None:
    ensure_ready()
    with connect() as connection:
        connection.execute(
            """
            UPDATE users
            SET last_login_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (user_id,),
        )


def save_auth_audit_event(
    event_type: str,
    success: bool,
    email: Optional[str] = None,
    user_id: Optional[str] = None,
    role: Optional[str] = None,
    detail: Optional[str] = None,
) -> None:
    ensure_ready()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO auth_audit_events (
                event_type,
                user_id,
                email,
                role,
                success,
                detail
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_type, user_id, email, role, 1 if success else 0, detail),
        )


def get_streaming_message(message_id: str) -> Optional[dict[str, Any]]:
    return _fetch_one("SELECT * FROM streaming_messages WHERE message_id = ?", (message_id,))


def save_streaming_message(
    message_id: str,
    source: str,
    message_type: str,
    subject: Optional[str],
    status: str,
    error: Optional[str] = None,
) -> None:
    ensure_ready()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO streaming_messages (
                message_id,
                source,
                message_type,
                subject,
                status,
                error
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(message_id) DO UPDATE SET
                source=excluded.source,
                message_type=excluded.message_type,
                subject=excluded.subject,
                status=excluded.status,
                error=excluded.error,
                received_at=CURRENT_TIMESTAMP
            """,
            (message_id, source, message_type, subject, status, error),
        )


def save_learning_interaction(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_ready()
    interaction_id = payload.get("id") or f"LINT-{uuid.uuid4().hex[:12].upper()}"
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO learning_interactions (
                id,
                assistant,
                interaction_type,
                user_id,
                user_role,
                equipment_id,
                work_order_id,
                prompt,
                response,
                provider,
                used_live_provider,
                prompt_version,
                model_version,
                source_refs,
                approved_for_learning,
                outcome_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                response=excluded.response,
                provider=excluded.provider,
                used_live_provider=excluded.used_live_provider,
                source_refs=excluded.source_refs,
                approved_for_learning=excluded.approved_for_learning,
                outcome_status=excluded.outcome_status
            """,
            (
                interaction_id,
                payload["assistant"],
                payload["interaction_type"],
                payload.get("user_id"),
                payload.get("user_role"),
                payload.get("equipment_id"),
                payload.get("work_order_id"),
                payload["prompt"],
                payload["response"],
                payload.get("provider") or "mock",
                1 if payload.get("used_live_provider") else 0,
                payload.get("prompt_version") or "default",
                payload.get("model_version") or "model-local-qwen2.5-current",
                _json_dump_any(payload.get("source_refs", [])),
                1 if payload.get("approved_for_learning") else 0,
                payload.get("outcome_status"),
            ),
        )
    interaction = get_learning_interaction(interaction_id)
    if not interaction:
        raise RuntimeError("Learning interaction was not persisted")
    return interaction


def get_learning_interaction(interaction_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one("SELECT * FROM learning_interactions WHERE id = ?", (interaction_id,))
    return _decode_learning_interaction(row) if row else None


def list_learning_interactions(
    approved_only: Optional[bool] = None,
    equipment_id: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if approved_only is not None:
        clauses.append("approved_for_learning = ?")
        params.append(1 if approved_only else 0)
    if equipment_id:
        clauses.append("equipment_id = ?")
        params.append(equipment_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    rows = _fetch_all(
        f"""
        SELECT * FROM learning_interactions
        {where}
        ORDER BY created_at DESC
        LIMIT ?
        """,
        tuple(params),
    )
    return [_decode_learning_interaction(row) for row in rows]


def upsert_learning_example(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_ready()
    example_id = payload.get("id") or f"LEX-{uuid.uuid4().hex[:12].upper()}"
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO learning_examples (
                id,
                source_type,
                source_id,
                equipment_id,
                work_order_id,
                instruction,
                input_text,
                expected_output,
                metadata,
                approved,
                judge_score,
                judge_label,
                judge_rationale,
                judge_provider,
                judge_used_live_provider,
                judged_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(source_type, source_id) DO UPDATE SET
                equipment_id=excluded.equipment_id,
                work_order_id=excluded.work_order_id,
                instruction=excluded.instruction,
                input_text=excluded.input_text,
                expected_output=excluded.expected_output,
                metadata=excluded.metadata,
                approved=excluded.approved,
                judge_score=excluded.judge_score,
                judge_label=excluded.judge_label,
                judge_rationale=excluded.judge_rationale,
                judge_provider=excluded.judge_provider,
                judge_used_live_provider=excluded.judge_used_live_provider,
                judged_at=CURRENT_TIMESTAMP
            """,
            (
                example_id,
                payload["source_type"],
                payload["source_id"],
                payload.get("equipment_id"),
                payload.get("work_order_id"),
                payload["instruction"],
                payload["input_text"],
                payload["expected_output"],
                _json_dump_any(payload.get("metadata", {})),
                1 if payload.get("approved") else 0,
                float(payload.get("judge_score") or 0),
                payload.get("judge_label") or "not_scored",
                payload.get("judge_rationale"),
                payload.get("judge_provider") or "not_scored",
                1 if payload.get("judge_used_live_provider") else 0,
            ),
        )
    example = get_learning_example_by_source(payload["source_type"], payload["source_id"])
    if not example:
        raise RuntimeError("Learning example was not persisted")
    return example


def get_learning_example(example_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one("SELECT * FROM learning_examples WHERE id = ?", (example_id,))
    return _decode_learning_example(row) if row else None


def get_learning_example_by_source(source_type: str, source_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one(
        "SELECT * FROM learning_examples WHERE source_type = ? AND source_id = ?",
        (source_type, source_id),
    )
    return _decode_learning_example(row) if row else None


def list_learning_examples(
    approved_only: Optional[bool] = None,
    equipment_id: Optional[str] = None,
    min_judge_score: Optional[float] = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if approved_only is not None:
        clauses.append("approved = ?")
        params.append(1 if approved_only else 0)
    if equipment_id:
        clauses.append("equipment_id = ?")
        params.append(equipment_id)
    if min_judge_score is not None:
        clauses.append("judge_score >= ?")
        params.append(min_judge_score)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    rows = _fetch_all(
        f"""
        SELECT * FROM learning_examples
        {where}
        ORDER BY approved DESC, created_at DESC
        LIMIT ?
        """,
        tuple(params),
    )
    return [_decode_learning_example(row) for row in rows]


def set_learning_example_approval(example_id: str, approved: bool) -> Optional[dict[str, Any]]:
    ensure_ready()
    with connect() as connection:
        connection.execute(
            "UPDATE learning_examples SET approved = ? WHERE id = ?",
            (1 if approved else 0, example_id),
        )
    return get_learning_example(example_id)


def update_learning_example_judgement(
    example_id: str,
    score: float,
    label: str,
    rationale: str,
    provider: str,
    used_live_provider: bool,
) -> Optional[dict[str, Any]]:
    ensure_ready()
    with connect() as connection:
        connection.execute(
            """
            UPDATE learning_examples
            SET
                judge_score = ?,
                judge_label = ?,
                judge_rationale = ?,
                judge_provider = ?,
                judge_used_live_provider = ?,
                judged_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (score, label, rationale, provider, 1 if used_live_provider else 0, example_id),
        )
    return get_learning_example(example_id)


def create_learning_dataset_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_ready()
    snapshot_id = payload.get("id") or f"LDS-{uuid.uuid4().hex[:12].upper()}"
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO learning_dataset_snapshots (
                id,
                name,
                description,
                example_count,
                approved_only,
                jsonl_content,
                created_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                payload["name"],
                payload.get("description"),
                payload["example_count"],
                1 if payload.get("approved_only", True) else 0,
                payload["jsonl_content"],
                payload.get("created_by"),
            ),
        )
    snapshot = get_learning_dataset_snapshot(snapshot_id)
    if not snapshot:
        raise RuntimeError("Learning dataset snapshot was not persisted")
    return snapshot


def get_learning_dataset_snapshot(snapshot_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one("SELECT * FROM learning_dataset_snapshots WHERE id = ?", (snapshot_id,))
    return _decode_learning_snapshot(row) if row else None


def list_learning_dataset_snapshots(limit: int = 20) -> list[dict[str, Any]]:
    rows = _fetch_all(
        """
        SELECT * FROM learning_dataset_snapshots
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [_decode_learning_snapshot(row) for row in rows]


def list_learning_model_versions() -> list[dict[str, Any]]:
    return _fetch_all("SELECT * FROM learning_model_versions ORDER BY created_at DESC")


def save_rag_embedding_profile(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_ready()
    profile_id = payload["id"]
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO rag_embedding_profiles (
                id,
                provider,
                model,
                version,
                dimensions,
                distance,
                status,
                notes,
                metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                provider=excluded.provider,
                model=excluded.model,
                version=excluded.version,
                dimensions=excluded.dimensions,
                distance=excluded.distance,
                status=excluded.status,
                notes=excluded.notes,
                metadata=excluded.metadata,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                profile_id,
                payload["provider"],
                payload["model"],
                payload["version"],
                int(payload["dimensions"]),
                payload["distance"],
                payload.get("status") or "candidate",
                payload.get("notes"),
                _json_dump_any(payload.get("metadata", {})),
            ),
        )
    profile = get_rag_embedding_profile(profile_id)
    if not profile:
        raise RuntimeError("RAG embedding profile was not persisted")
    return profile


def list_rag_embedding_profiles() -> list[dict[str, Any]]:
    rows = _fetch_all(
        """
        SELECT * FROM rag_embedding_profiles
        ORDER BY
          CASE status WHEN 'active' THEN 0 WHEN 'candidate' THEN 1 ELSE 2 END,
          updated_at DESC,
          created_at DESC
        """
    )
    return [_decode_rag_embedding_profile(row) for row in rows]


def get_rag_embedding_profile(profile_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one("SELECT * FROM rag_embedding_profiles WHERE id = ?", (profile_id,))
    return _decode_rag_embedding_profile(row) if row else None


def get_active_rag_embedding_profile() -> Optional[dict[str, Any]]:
    row = _fetch_one(
        """
        SELECT * FROM rag_embedding_profiles
        WHERE status = 'active'
        ORDER BY updated_at DESC, created_at DESC
        LIMIT 1
        """
    )
    return _decode_rag_embedding_profile(row) if row else None


def activate_rag_embedding_profile(profile_id: str) -> Optional[dict[str, Any]]:
    ensure_ready()
    profile = get_rag_embedding_profile(profile_id)
    if not profile:
        return None
    with connect() as connection:
        connection.execute(
            """
            UPDATE rag_embedding_profiles
            SET status = 'candidate',
                updated_at = CURRENT_TIMESTAMP
            WHERE status = 'active'
              AND id <> ?
            """,
            (profile_id,),
        )
        connection.execute(
            """
            UPDATE rag_embedding_profiles
            SET status = 'active',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (profile_id,),
        )
    return get_rag_embedding_profile(profile_id)


def get_active_learning_model_version() -> Optional[dict[str, Any]]:
    row = _fetch_one(
        """
        SELECT * FROM learning_model_versions
        WHERE status = 'active'
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    return dict(row) if row else None


def get_learning_model_version(model_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one("SELECT * FROM learning_model_versions WHERE id = ?", (model_id,))
    return dict(row) if row else None


def save_learning_model_version(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_ready()
    model_id = payload.get("id") or f"model-{uuid.uuid4().hex[:12].lower()}"
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO learning_model_versions (
                id,
                provider,
                model_name,
                base_model,
                adapter_path,
                status,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                provider=excluded.provider,
                model_name=excluded.model_name,
                base_model=excluded.base_model,
                adapter_path=excluded.adapter_path,
                status=excluded.status,
                notes=excluded.notes
            """,
            (
                model_id,
                payload["provider"],
                payload["model_name"],
                payload.get("base_model"),
                payload.get("adapter_path"),
                payload.get("status") or "candidate",
                payload.get("notes"),
            ),
        )
    model = _fetch_one("SELECT * FROM learning_model_versions WHERE id = ?", (model_id,))
    if not model:
        raise RuntimeError("Learning model version was not persisted")
    return dict(model)


def set_learning_model_status(model_id: str, status: str, notes: Optional[str] = None) -> Optional[dict[str, Any]]:
    ensure_ready()
    existing = get_learning_model_version(model_id)
    if not existing:
        return None
    next_notes = notes if notes is not None else existing.get("notes")
    with connect() as connection:
        connection.execute(
            """
            UPDATE learning_model_versions
            SET status = ?, notes = ?
            WHERE id = ?
            """,
            (status, next_notes, model_id),
        )
    return get_learning_model_version(model_id)


def list_learning_prompt_versions() -> list[dict[str, Any]]:
    return _fetch_all("SELECT * FROM learning_prompt_versions ORDER BY assistant ASC, created_at DESC")


def get_learning_prompt_version(prompt_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one("SELECT * FROM learning_prompt_versions WHERE id = ?", (prompt_id,))
    return dict(row) if row else None


def save_learning_evaluation_run(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_ready()
    run_id = payload.get("id") or f"LEVAL-{uuid.uuid4().hex[:12].upper()}"
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO learning_evaluation_runs (
                id,
                dataset_id,
                model_version_id,
                prompt_version_id,
                metrics,
                notes,
                passed
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                payload.get("dataset_id"),
                payload.get("model_version_id"),
                payload.get("prompt_version_id"),
                _json_dump_any(payload.get("metrics", {})),
                payload.get("notes"),
                1 if payload.get("passed") else 0,
            ),
        )
    run = get_learning_evaluation_run(run_id)
    if not run:
        raise RuntimeError("Learning evaluation run was not persisted")
    return run


def get_learning_evaluation_run(run_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one("SELECT * FROM learning_evaluation_runs WHERE id = ?", (run_id,))
    return _decode_learning_evaluation(row) if row else None


def list_learning_evaluation_runs(limit: int = 20) -> list[dict[str, Any]]:
    rows = _fetch_all(
        """
        SELECT * FROM learning_evaluation_runs
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [_decode_learning_evaluation(row) for row in rows]


def save_learning_model_promotion(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_ready()
    promotion_id = payload.get("id") or f"LPROMO-{uuid.uuid4().hex[:12].upper()}"
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO learning_model_promotions (
                id,
                model_version_id,
                previous_active_model_id,
                evaluation_run_id,
                dataset_id,
                prompt_version_id,
                action,
                reviewer_email,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                promotion_id,
                payload["model_version_id"],
                payload.get("previous_active_model_id"),
                payload["evaluation_run_id"],
                payload["dataset_id"],
                payload["prompt_version_id"],
                payload["action"],
                payload["reviewer_email"],
                payload.get("notes"),
            ),
        )
    promotion = get_learning_model_promotion(promotion_id)
    if not promotion:
        raise RuntimeError("Learning model promotion was not persisted")
    return promotion


def get_learning_model_promotion(promotion_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one("SELECT * FROM learning_model_promotions WHERE id = ?", (promotion_id,))
    return dict(row) if row else None


def list_learning_model_promotions(limit: int = 20) -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT * FROM learning_model_promotions
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    )


def save_learning_model_deployment(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_ready()
    deployment_id = payload.get("id") or f"LDEP-{uuid.uuid4().hex[:12].upper()}"
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO learning_model_deployments (
                id,
                model_version_id,
                job_id,
                runtime_provider,
                serving_provider,
                served_model_name,
                base_url,
                artifact_uri,
                artifact_hash,
                status,
                health_status,
                health_checked_at,
                metadata,
                error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                model_version_id=excluded.model_version_id,
                job_id=excluded.job_id,
                runtime_provider=excluded.runtime_provider,
                serving_provider=excluded.serving_provider,
                served_model_name=excluded.served_model_name,
                base_url=excluded.base_url,
                artifact_uri=excluded.artifact_uri,
                artifact_hash=excluded.artifact_hash,
                status=excluded.status,
                health_status=excluded.health_status,
                health_checked_at=excluded.health_checked_at,
                metadata=excluded.metadata,
                error=excluded.error,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                deployment_id,
                payload["model_version_id"],
                payload.get("job_id"),
                payload["runtime_provider"],
                payload["serving_provider"],
                payload["served_model_name"],
                payload.get("base_url"),
                payload.get("artifact_uri"),
                payload.get("artifact_hash"),
                payload.get("status") or "pending",
                payload.get("health_status"),
                payload.get("health_checked_at"),
                _json_dump_any(payload.get("metadata", {})),
                payload.get("error"),
            ),
        )
    deployment = get_learning_model_deployment(deployment_id)
    if not deployment:
        raise RuntimeError("Learning model deployment was not persisted")
    return deployment


def get_learning_model_deployment(deployment_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one("SELECT * FROM learning_model_deployments WHERE id = ?", (deployment_id,))
    return _decode_learning_model_deployment(row) if row else None


def list_learning_model_deployments(
    *,
    model_version_id: Optional[str] = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    if model_version_id:
        rows = _fetch_all(
            """
            SELECT * FROM learning_model_deployments
            WHERE model_version_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (model_version_id, limit),
        )
    else:
        rows = _fetch_all(
            """
            SELECT * FROM learning_model_deployments
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
    return [_decode_learning_model_deployment(row) for row in rows]


def get_verified_learning_model_deployment(model_version_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one(
        """
        SELECT * FROM learning_model_deployments
        WHERE model_version_id = ?
          AND status = 'verified'
          AND health_status IN ('healthy', 'manual_verified')
        ORDER BY health_checked_at DESC, created_at DESC
        LIMIT 1
        """,
        (model_version_id,),
    )
    return _decode_learning_model_deployment(row) if row else None


def save_learning_job(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_ready()
    job_id = payload.get("id") or f"LJOB-{uuid.uuid4().hex[:12].upper()}"
    correlation_id = payload.get("correlation_id") or job_id
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO learning_jobs (
                id,
                job_type,
                subject,
                status,
                requested_by,
                correlation_id,
                input_refs,
                output_refs,
                error,
                retry_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                job_type=excluded.job_type,
                subject=excluded.subject,
                status=excluded.status,
                requested_by=excluded.requested_by,
                correlation_id=excluded.correlation_id,
                input_refs=excluded.input_refs,
                output_refs=excluded.output_refs,
                error=excluded.error,
                retry_count=excluded.retry_count,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                job_id,
                payload["job_type"],
                payload["subject"],
                payload.get("status") or "queued",
                payload.get("requested_by"),
                correlation_id,
                _json_dump_any(payload.get("input_refs", {})),
                _json_dump_any(payload.get("output_refs", {})),
                payload.get("error"),
                int(payload.get("retry_count") or 0),
            ),
        )
    job = get_learning_job(job_id)
    if not job:
        raise RuntimeError("Learning job was not persisted")
    return job


def update_learning_job_status(
    job_id: str,
    status: str,
    *,
    output_refs: Optional[dict[str, Any]] = None,
    error: Optional[str] = None,
    retry_count: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    ensure_ready()
    existing = get_learning_job(job_id)
    if not existing:
        return None
    next_output_refs = output_refs if output_refs is not None else existing.get("output_refs", {})
    next_retry_count = retry_count if retry_count is not None else existing.get("retry_count", 0)
    with connect() as connection:
        connection.execute(
            """
            UPDATE learning_jobs
            SET status = ?,
                output_refs = ?,
                error = ?,
                retry_count = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                status,
                _json_dump_any(next_output_refs),
                error,
                int(next_retry_count or 0),
                job_id,
            ),
        )
    return get_learning_job(job_id)


def get_learning_job(job_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one("SELECT * FROM learning_jobs WHERE id = ?", (job_id,))
    return _decode_learning_job(row) if row else None


def list_learning_jobs(limit: int = 20, status: Optional[str] = None) -> list[dict[str, Any]]:
    if status:
        rows = _fetch_all(
            """
            SELECT * FROM learning_jobs
            WHERE status = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (status, limit),
        )
    else:
        rows = _fetch_all(
            """
            SELECT * FROM learning_jobs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
    return [_decode_learning_job(row) for row in rows]


def save_learning_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_ready()
    artifact_id = payload.get("id") or f"LART-{uuid.uuid4().hex[:12].upper()}"
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO learning_artifacts (
                id,
                job_id,
                artifact_type,
                uri,
                content_hash,
                metadata
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                job_id=excluded.job_id,
                artifact_type=excluded.artifact_type,
                uri=excluded.uri,
                content_hash=excluded.content_hash,
                metadata=excluded.metadata
            """,
            (
                artifact_id,
                payload["job_id"],
                payload["artifact_type"],
                payload["uri"],
                payload["content_hash"],
                _json_dump_any(payload.get("metadata", {})),
            ),
        )
    artifact = get_learning_artifact(artifact_id)
    if not artifact:
        raise RuntimeError("Learning artifact was not persisted")
    return artifact


def get_learning_artifact(artifact_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one("SELECT * FROM learning_artifacts WHERE id = ?", (artifact_id,))
    return _decode_learning_artifact(row) if row else None


def list_learning_artifacts(job_id: Optional[str] = None, limit: int = 20) -> list[dict[str, Any]]:
    if job_id:
        rows = _fetch_all(
            """
            SELECT * FROM learning_artifacts
            WHERE job_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (job_id, limit),
        )
    else:
        rows = _fetch_all(
            """
            SELECT * FROM learning_artifacts
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
    return [_decode_learning_artifact(row) for row in rows]


def learning_counts() -> dict[str, int]:
    rows = _fetch_all(
        """
        SELECT 'interactions' AS name, COUNT(*) AS count FROM learning_interactions
        UNION ALL
        SELECT 'examples' AS name, COUNT(*) AS count FROM learning_examples
        UNION ALL
        SELECT 'approved_examples' AS name, COUNT(*) AS count FROM learning_examples WHERE approved = 1
        UNION ALL
        SELECT 'snapshots' AS name, COUNT(*) AS count FROM learning_dataset_snapshots
        UNION ALL
        SELECT 'model_versions' AS name, COUNT(*) AS count FROM learning_model_versions
        UNION ALL
        SELECT 'prompt_versions' AS name, COUNT(*) AS count FROM learning_prompt_versions
        UNION ALL
        SELECT 'evaluation_runs' AS name, COUNT(*) AS count FROM learning_evaluation_runs
        UNION ALL
        SELECT 'jobs' AS name, COUNT(*) AS count FROM learning_jobs
        UNION ALL
        SELECT 'queued_jobs' AS name, COUNT(*) AS count FROM learning_jobs WHERE status IN ('queued', 'published', 'running')
        UNION ALL
        SELECT 'artifacts' AS name, COUNT(*) AS count FROM learning_artifacts
        UNION ALL
        SELECT 'deployments' AS name, COUNT(*) AS count FROM learning_model_deployments
        UNION ALL
        SELECT 'promotions' AS name, COUNT(*) AS count FROM learning_model_promotions
        UNION ALL
        SELECT 'embedding_profiles' AS name, COUNT(*) AS count FROM rag_embedding_profiles
        """
    )
    return {row["name"]: int(row["count"]) for row in rows}


def _normalize_user(user: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not user:
        return None
    normalized = dict(user)
    normalized["is_active"] = bool(normalized["is_active"])
    return normalized


def _json_dump(value: Any) -> str:
    return json.dumps(value or [], separators=(",", ":"))


def _json_dump_any(value: Any) -> str:
    return json.dumps(value if value is not None else {}, separators=(",", ":"))


def _json_load_list(value: Any) -> list[str]:
    if not value:
        return []
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return []
    if not isinstance(decoded, list):
        return []
    return [str(item) for item in decoded if str(item).strip()]


def _json_load_dict(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _json_load_any(value: Any) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _decode_document_intelligence(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    for field in (
        "asset_ids",
        "components",
        "failure_modes",
        "symptoms",
        "safety_constraints",
        "spares",
        "thresholds",
    ):
        decoded[field] = _json_load_list(decoded.get(field))
    decoded["used_live_provider"] = bool(decoded.get("used_live_provider"))
    return decoded


def _decode_maintenance_label(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    decoded["signal_hints"] = _json_load_list(decoded.get("signal_hints"))
    decoded["usable_for_training"] = bool(decoded.get("usable_for_training"))
    decoded["used_live_provider"] = bool(decoded.get("used_live_provider"))
    return decoded


def _decode_learning_interaction(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    decoded["source_refs"] = _json_load_any(decoded.get("source_refs")) or []
    decoded["used_live_provider"] = bool(decoded.get("used_live_provider"))
    decoded["approved_for_learning"] = bool(decoded.get("approved_for_learning"))
    return decoded


def _decode_learning_example(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    decoded["metadata"] = _json_load_dict(decoded.get("metadata"))
    decoded["approved"] = bool(decoded.get("approved"))
    decoded["judge_score"] = float(decoded.get("judge_score") or 0)
    decoded["judge_used_live_provider"] = bool(decoded.get("judge_used_live_provider"))
    return decoded


def _decode_learning_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    decoded["approved_only"] = bool(decoded.get("approved_only"))
    return decoded


def _decode_learning_evaluation(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    decoded["metrics"] = _json_load_dict(decoded.get("metrics"))
    decoded["passed"] = bool(decoded.get("passed"))
    return decoded


def _decode_learning_job(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    decoded["input_refs"] = _json_load_dict(decoded.get("input_refs"))
    decoded["output_refs"] = _json_load_dict(decoded.get("output_refs"))
    decoded["retry_count"] = int(decoded.get("retry_count") or 0)
    return decoded


def _decode_learning_artifact(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    decoded["metadata"] = _json_load_dict(decoded.get("metadata"))
    return decoded


def _decode_rag_embedding_profile(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    decoded["dimensions"] = int(decoded.get("dimensions") or 0)
    decoded["metadata"] = _json_load_dict(decoded.get("metadata"))
    return decoded


def _decode_learning_model_deployment(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    decoded["metadata"] = _json_load_dict(decoded.get("metadata"))
    return decoded


def _decode_work_order(row: dict[str, Any], include_logs: bool) -> dict[str, Any]:
    decoded = dict(row)
    decoded["follow_up_required"] = bool(decoded.get("follow_up_required"))
    if include_logs:
        decoded["logs"] = _fetch_all(
            "SELECT * FROM work_order_logs WHERE work_order_id = ? ORDER BY created_at ASC, id ASC",
            (decoded["id"],),
        )
    else:
        decoded["logs"] = []
    return decoded


def _next_work_order_id() -> str:
    rows = _fetch_all("SELECT id FROM work_orders WHERE id LIKE 'WO-%'")
    numeric_ids: list[int] = []
    for row in rows:
        try:
            numeric_ids.append(int(str(row["id"]).split("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    next_number = max(numeric_ids, default=8300) + 1
    return f"WO-{next_number}"


def _fetch_all(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    ensure_ready()
    with connect() as connection:
        return [dict(row) for row in connection.execute(sql, params).fetchall()]


def _fetch_one(sql: str, params: tuple[Any, ...] = ()) -> Optional[dict[str, Any]]:
    ensure_ready()
    with connect() as connection:
        row = connection.execute(sql, params).fetchone()
        return dict(row) if row else None
