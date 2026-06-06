from typing import Any, Optional

import sqlite3

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


def _fetch_all(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    ensure_ready()
    with connect() as connection:
        return [dict(row) for row in connection.execute(sql, params).fetchall()]


def _fetch_one(sql: str, params: tuple[Any, ...] = ()) -> Optional[dict[str, Any]]:
    ensure_ready()
    with connect() as connection:
        row = connection.execute(sql, params).fetchone()
        return dict(row) if row else None
