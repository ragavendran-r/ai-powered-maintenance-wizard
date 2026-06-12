import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.core.config import get_settings
from app.core.security import hash_password
from app.data.sample_loader import load_sample_data


DEMO_USER_PASSWORD = "DemoPass123!"
DEMO_USERS = [
    {
        "id": "USER-ADMIN",
        "email": "admin@plant.local",
        "display_name": "Plant Admin",
        "role": "admin",
    },
    {
        "id": "USER-MAINTENANCE",
        "email": "maintenance@plant.local",
        "display_name": "Maintenance Engineer",
        "role": "maintenance_engineer",
    },
    {
        "id": "USER-RELIABILITY",
        "email": "reliability@plant.local",
        "display_name": "Reliability Engineer",
        "role": "reliability_engineer",
    },
    {
        "id": "USER-PLANNER",
        "email": "planner@plant.local",
        "display_name": "Maintenance Planner",
        "role": "planner",
    },
    {
        "id": "USER-OPERATOR",
        "email": "operator@plant.local",
        "display_name": "Shift Operator",
        "role": "operator",
    },
    {
        "id": "USER-IOT-SERVICE",
        "email": "iot-service@plant.local",
        "display_name": "IoT Service Account",
        "role": "iot_service",
    },
]


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
    CREATE TABLE IF NOT EXISTS work_orders (
        id TEXT PRIMARY KEY,
        equipment_id TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        status TEXT NOT NULL,
        priority INTEGER NOT NULL,
        work_type TEXT NOT NULL,
        failure_class TEXT NOT NULL,
        problem_code TEXT NOT NULL,
        classification TEXT NOT NULL,
        assigned_to TEXT NOT NULL,
        supervisor TEXT NOT NULL,
        due_date TEXT NOT NULL,
        recommended_action TEXT NOT NULL,
        follow_up_required INTEGER NOT NULL DEFAULT 0,
        ai_summary TEXT,
        completion_summary TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT,
        FOREIGN KEY (equipment_id) REFERENCES equipment(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS work_order_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        work_order_id TEXT NOT NULL,
        author TEXT NOT NULL,
        entry_type TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (work_order_id) REFERENCES work_orders(id)
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
        equipment_id TEXT,
        status TEXT NOT NULL,
        corrected_diagnosis TEXT,
        actual_root_cause TEXT,
        action_taken TEXT,
        outcome TEXT,
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS document_intelligence (
        document_id TEXT PRIMARY KEY,
        summary TEXT NOT NULL,
        asset_ids TEXT NOT NULL,
        components TEXT NOT NULL,
        failure_modes TEXT NOT NULL,
        symptoms TEXT NOT NULL,
        safety_constraints TEXT NOT NULL,
        spares TEXT NOT NULL,
        thresholds TEXT NOT NULL,
        used_live_provider INTEGER NOT NULL DEFAULT 0,
        provider TEXT NOT NULL DEFAULT 'mock',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (document_id) REFERENCES documents(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS maintenance_labels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_type TEXT NOT NULL,
        source_id TEXT NOT NULL,
        equipment_id TEXT,
        failure_mode TEXT NOT NULL,
        component TEXT NOT NULL,
        root_cause TEXT NOT NULL,
        action_class TEXT NOT NULL,
        outcome_status TEXT NOT NULL,
        signal_hints TEXT NOT NULL,
        usable_for_training INTEGER NOT NULL DEFAULT 1,
        used_live_provider INTEGER NOT NULL DEFAULT 0,
        provider TEXT NOT NULL DEFAULT 'mock',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(source_type, source_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS streaming_messages (
        message_id TEXT PRIMARY KEY,
        source TEXT NOT NULL,
        message_type TEXT NOT NULL,
        subject TEXT,
        status TEXT NOT NULL,
        error TEXT,
        received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        display_name TEXT NOT NULL,
        role TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_login_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_audit_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        user_id TEXT,
        email TEXT,
        role TEXT,
        success INTEGER NOT NULL,
        detail TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """,
]

SCHEMA_VERSION = "6"


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
        _ensure_column(connection, "feedback", "equipment_id", "TEXT")
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
            if get_settings().auth_seed_demo_users:
                seed_demo_users(connection)


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
    seed_demo_work_orders(connection)
    from app.data.repository import rebuild_document_chunks

    rebuild_document_chunks(connection)


def seed_demo_work_orders(connection: sqlite3.Connection) -> None:
    work_orders = [
        {
            "id": "WO-8304",
            "equipment_id": "RM-DRIVE-01",
            "title": "Inspect main drive bearing vibration",
            "description": "Inspect drive-end bearing housing, coupling alignment, lubrication condition, and foundation bolts after critical vibration alert.",
            "status": "INPRG",
            "priority": 1,
            "work_type": "CM",
            "failure_class": "MECH",
            "problem_code": "BRGVIB",
            "classification": "Bearing vibration",
            "assigned_to": "Maintenance Engineer",
            "supervisor": "Maintenance Supervisor",
            "due_date": "2026-06-12T18:00:00+05:30",
            "recommended_action": "Reduce load if vibration persists, inspect bearing housing temperature, verify coupling alignment, and document final root cause.",
            "follow_up_required": True,
            "ai_summary": "High-risk drive vibration with unavailable bearing spare; technician should verify mechanical looseness and bearing condition before restart.",
            "completion_summary": None,
            "completed_at": None,
        },
        {
            "id": "WO-8311",
            "equipment_id": "BF-BLOWER-02",
            "title": "Verify inlet guide vane actuator response",
            "description": "Check actuator travel, linkage looseness, position feedback drift, and pressure variance on combustion air blower.",
            "status": "APPR",
            "priority": 2,
            "work_type": "CM",
            "failure_class": "CTRL",
            "problem_code": "IGVACT",
            "classification": "Control actuator",
            "assigned_to": "Reliability Engineer",
            "supervisor": "Blast Furnace Supervisor",
            "due_date": "2026-06-13T12:00:00+05:30",
            "recommended_action": "Stroke-test the guide vane actuator and compare position feedback with outlet pressure variance trend.",
            "follow_up_required": False,
            "ai_summary": "Pressure variance suggests guide vane actuator or linkage response drift.",
            "completion_summary": None,
            "completed_at": None,
        },
        {
            "id": "WO-8297",
            "equipment_id": "OH-CRANE-05",
            "title": "Inspect hoist brake temperature and current",
            "description": "Restrict heavy lifts until hoist brake shoes, motor current, and brake temperature are inspected.",
            "status": "COMP",
            "priority": 1,
            "work_type": "EM",
            "failure_class": "ELEC",
            "problem_code": "HOISTBRK",
            "classification": "Hoist braking",
            "assigned_to": "Crane Technician",
            "supervisor": "Melt Shop Supervisor",
            "due_date": "2026-06-11T17:00:00+05:30",
            "recommended_action": "Confirm brake shoe wear and motor current after lift restriction.",
            "follow_up_required": True,
            "ai_summary": "Completed crane inspection still requires supervisor follow-up because brake spares are unavailable.",
            "completion_summary": "Brake temperature was verified after load restriction; follow-up is required for brake shoe replacement planning.",
            "completed_at": "2026-06-11T16:35:00+05:30",
        },
        {
            "id": "WO-8275",
            "equipment_id": "HYD-SYS-04",
            "title": "Investigate hydraulic oil temperature rise",
            "description": "Inspect cooler fouling, pump cartridge condition, and pressure pulsation during roll gap correction.",
            "status": "WMATL",
            "priority": 2,
            "work_type": "PM",
            "failure_class": "HYD",
            "problem_code": "OILTEMP",
            "classification": "Hydraulic temperature",
            "assigned_to": "Hydraulic Technician",
            "supervisor": "Rolling Mill Supervisor",
            "due_date": "2026-06-14T10:00:00+05:30",
            "recommended_action": "Reserve pump cartridge assembly, inspect cooler differential temperature, and trend pressure pulsation.",
            "follow_up_required": False,
            "ai_summary": "Hydraulic oil temperature and pressure pulsation require material coordination before intrusive work.",
            "completion_summary": None,
            "completed_at": None,
        },
    ]
    columns = [
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
    ]
    _insert_many(connection, "work_orders", columns, work_orders)
    connection.execute("DELETE FROM work_order_logs WHERE work_order_id IN ('WO-8304', 'WO-8297')")
    connection.executemany(
        """
        INSERT INTO work_order_logs (work_order_id, author, entry_type, content)
        VALUES (?, ?, ?, ?)
        """,
        [
            ("WO-8304", "Maintenance Wizard", "assistant", "Start with lockout, bearing temperature, coupling alignment, and foundation bolt checks."),
            ("WO-8304", "Maintenance Engineer", "observation", "Drive-end vibration confirmed at reduced finishing stand load."),
            ("WO-8297", "Crane Technician", "completion", "Brake temperature normalized after restriction; shoe set needs follow-up replacement planning."),
        ],
    )


def seed_demo_users(connection: sqlite3.Connection) -> None:
    password_hash = hash_password(DEMO_USER_PASSWORD)
    connection.executemany(
        """
        INSERT INTO users (
            id,
            email,
            display_name,
            role,
            password_hash,
            is_active
        )
        VALUES (?, ?, ?, ?, ?, 1)
        ON CONFLICT(email) DO NOTHING
        """,
        [
            (
                user["id"],
                user["email"],
                user["display_name"],
                user["role"],
                password_hash,
            )
            for user in DEMO_USERS
        ],
    )


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
        "work_orders",
        "work_order_logs",
        "documents",
        "document_chunks",
        "document_intelligence",
        "feedback",
        "maintenance_labels",
        "streaming_messages",
        "users",
        "auth_audit_events",
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


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
