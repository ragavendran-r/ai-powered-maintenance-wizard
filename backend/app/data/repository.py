from typing import Any, Optional

import sqlite3
import uuid

from app.core.security import hash_password
from app.data.database import connect, initialize_database
from app.services.vector_index import build_chunks_for_document


def ensure_ready() -> None:
    initialize_database(seed=True)


def list_equipment() -> list[dict[str, Any]]:
    return _fetch_all("SELECT * FROM equipment ORDER BY criticality DESC, name ASC")


def get_equipment(equipment_id: str) -> Optional[dict[str, Any]]:
    return _fetch_one("SELECT * FROM equipment WHERE id = ?", (equipment_id,))


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


def list_documents(equipment_id: Optional[str] = None) -> list[dict[str, Any]]:
    if equipment_id:
        return _fetch_all(
            "SELECT * FROM documents WHERE equipment_id = ? OR equipment_id IS NULL ORDER BY source_type, title",
            (equipment_id,),
        )
    return _fetch_all("SELECT * FROM documents ORDER BY source_type, title")


def list_document_chunks(equipment_id: Optional[str] = None) -> list[dict[str, Any]]:
    if equipment_id:
        return _fetch_all(
            """
            SELECT * FROM document_chunks
            WHERE equipment_id = ? OR equipment_id IS NULL
            ORDER BY source_type, title, chunk_index
            """,
            (equipment_id,),
        )
    return _fetch_all("SELECT * FROM document_chunks ORDER BY source_type, title, chunk_index")


def add_documents(documents: list[dict[str, Any]]) -> int:
    ensure_ready()
    if not documents:
        return 0
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
        upsert_document_chunks(connection, documents)
    return len(documents)


def rebuild_document_chunks(connection: sqlite3.Connection) -> None:
    documents = [dict(row) for row in connection.execute("SELECT * FROM documents").fetchall()]
    connection.execute("DELETE FROM document_chunks")
    upsert_document_chunks(connection, documents)


def upsert_document_chunks(connection: sqlite3.Connection, documents: list[dict[str, Any]]) -> None:
    if not documents:
        return
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
            embedding
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            document_id=excluded.document_id,
            chunk_index=excluded.chunk_index,
            source_type=excluded.source_type,
            equipment_id=excluded.equipment_id,
            title=excluded.title,
            content=excluded.content,
            embedding=excluded.embedding
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
            )
            for chunk in chunk_rows
        ],
    )


def add_records(payload: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    ensure_ready()
    table_columns = {
        "equipment": ["id", "name", "area", "process", "criticality", "status"],
        "alerts": ["id", "equipment_id", "timestamp", "signal", "value", "unit", "threshold", "severity", "message"],
        "spares": ["id", "equipment_id", "name", "available_qty", "lead_time_days", "criticality"],
        "sensor_readings": ["id", "equipment_id", "timestamp", "signal", "value", "unit", "threshold"],
        "maintenance_events": ["id", "equipment_id", "date", "issue", "root_cause", "action", "downtime_hours"],
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


def _normalize_user(user: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not user:
        return None
    normalized = dict(user)
    normalized["is_active"] = bool(normalized["is_active"])
    return normalized


def _fetch_all(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    ensure_ready()
    with connect() as connection:
        return [dict(row) for row in connection.execute(sql, params).fetchall()]


def _fetch_one(sql: str, params: tuple[Any, ...] = ()) -> Optional[dict[str, Any]]:
    ensure_ready()
    with connect() as connection:
        row = connection.execute(sql, params).fetchone()
        return dict(row) if row else None
