import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.core.config import get_settings
from app.data.sample_loader import load_sample_data


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS schema_metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS equipment (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        area TEXT NOT NULL,
        process TEXT NOT NULL,
        criticality INTEGER NOT NULL,
        status TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS alerts (
        id TEXT PRIMARY KEY,
        equipment_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        signal TEXT NOT NULL,
        value REAL NOT NULL,
        unit TEXT NOT NULL,
        threshold REAL NOT NULL,
        severity TEXT NOT NULL,
        message TEXT NOT NULL,
        FOREIGN KEY (equipment_id) REFERENCES equipment(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS spares (
        id TEXT PRIMARY KEY,
        equipment_id TEXT NOT NULL,
        name TEXT NOT NULL,
        available_qty INTEGER NOT NULL,
        lead_time_days INTEGER NOT NULL,
        criticality INTEGER NOT NULL,
        FOREIGN KEY (equipment_id) REFERENCES equipment(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sensor_readings (
        id TEXT PRIMARY KEY,
        equipment_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        signal TEXT NOT NULL,
        value REAL NOT NULL,
        unit TEXT NOT NULL,
        threshold REAL NOT NULL,
        FOREIGN KEY (equipment_id) REFERENCES equipment(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS maintenance_events (
        id TEXT PRIMARY KEY,
        equipment_id TEXT NOT NULL,
        date TEXT NOT NULL,
        issue TEXT NOT NULL,
        root_cause TEXT NOT NULL,
        action TEXT NOT NULL,
        downtime_hours REAL NOT NULL,
        FOREIGN KEY (equipment_id) REFERENCES equipment(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        source_type TEXT NOT NULL,
        equipment_id TEXT,
        title TEXT NOT NULL,
        content TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS document_chunks (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        source_type TEXT NOT NULL,
        equipment_id TEXT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        embedding TEXT NOT NULL,
        FOREIGN KEY (document_id) REFERENCES documents(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recommendation_id TEXT NOT NULL,
        status TEXT NOT NULL,
        corrected_diagnosis TEXT,
        actual_root_cause TEXT,
        action_taken TEXT,
        outcome TEXT,
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
]

SCHEMA_VERSION = "1"


def get_database_path() -> Path:
    return get_settings().database_path


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    db_path = get_database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def initialize_database(seed: bool = True) -> None:
    with connect() as connection:
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
        connection.execute(
            """
            INSERT INTO schema_metadata (key, value)
            VALUES ('schema_version', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (SCHEMA_VERSION,),
        )
        if seed:
            seed_from_sample_data(connection)


def seed_from_sample_data(connection: sqlite3.Connection) -> None:
    data = load_sample_data()
    _insert_many(
        connection,
        "equipment",
        ["id", "name", "area", "process", "criticality", "status"],
        data["equipment"],
    )
    _insert_many(
        connection,
        "alerts",
        ["id", "equipment_id", "timestamp", "signal", "value", "unit", "threshold", "severity", "message"],
        data["alerts"],
    )
    _insert_many(
        connection,
        "spares",
        ["id", "equipment_id", "name", "available_qty", "lead_time_days", "criticality"],
        data["spares"],
    )
    _insert_many(
        connection,
        "sensor_readings",
        ["id", "equipment_id", "timestamp", "signal", "value", "unit", "threshold"],
        data.get("sensor_readings", []),
    )
    _insert_many(
        connection,
        "maintenance_events",
        ["id", "equipment_id", "date", "issue", "root_cause", "action", "downtime_hours"],
        data["maintenance_events"],
    )
    _insert_many(
        connection,
        "documents",
        ["id", "source_type", "equipment_id", "title", "content"],
        data["documents"],
    )
    from app.data.repository import rebuild_document_chunks

    rebuild_document_chunks(connection)


def reset_database() -> None:
    db_path = get_database_path()
    if db_path.exists():
        db_path.unlink()
    initialize_database(seed=True)


def database_status() -> dict[str, Any]:
    initialize_database(seed=False)
    tables = [
        "equipment",
        "alerts",
        "sensor_readings",
        "spares",
        "maintenance_events",
        "documents",
        "document_chunks",
        "feedback",
    ]
    with connect() as connection:
        version_row = connection.execute(
            "SELECT value FROM schema_metadata WHERE key = 'schema_version'"
        ).fetchone()
        counts = {
            table: connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            for table in tables
        }
    return {
        "database_path": str(get_database_path()),
        "schema_version": version_row["value"] if version_row else "unknown",
        "counts": counts,
    }


def _insert_many(connection: sqlite3.Connection, table: str, columns: list[str], rows: list[dict[str, Any]]) -> None:
    placeholders = ", ".join(["?"] * len(columns))
    column_sql = ", ".join(columns)
    update_sql = ", ".join(f"{column}=excluded.{column}" for column in columns if column != "id")
    sql = f"""
        INSERT INTO {table} ({column_sql})
        VALUES ({placeholders})
        ON CONFLICT(id) DO UPDATE SET {update_sql}
    """
    values = [[_db_value(row.get(column)) for column in columns] for row in rows]
    connection.executemany(sql, values)


def _db_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value
