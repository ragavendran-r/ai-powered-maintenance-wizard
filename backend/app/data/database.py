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
    CREATE TABLE IF NOT EXISTS asset_profiles (
        equipment_id TEXT PRIMARY KEY,
        asset_type TEXT NOT NULL,
        location_code TEXT NOT NULL,
        location_name TEXT NOT NULL,
        parent_system TEXT NOT NULL,
        manufacturer TEXT NOT NULL,
        model TEXT NOT NULL,
        serial_number TEXT NOT NULL,
        installed_at TEXT NOT NULL,
        owner_team TEXT NOT NULL,
        supervisor TEXT NOT NULL,
        description TEXT NOT NULL,
        last_updated TEXT NOT NULL,
        FOREIGN KEY (equipment_id) REFERENCES equipment(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS asset_metric_snapshots (
        id TEXT PRIMARY KEY,
        equipment_id TEXT NOT NULL,
        metric_key TEXT NOT NULL,
        label TEXT NOT NULL,
        value REAL NOT NULL,
        unit TEXT NOT NULL,
        target_value REAL,
        status TEXT NOT NULL,
        trend TEXT NOT NULL,
        detail TEXT NOT NULL,
        captured_at TEXT NOT NULL,
        sort_order INTEGER NOT NULL,
        FOREIGN KEY (equipment_id) REFERENCES equipment(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS asset_recommendations (
        id TEXT PRIMARY KEY,
        equipment_id TEXT NOT NULL,
        action_type TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        priority INTEGER NOT NULL,
        source TEXT NOT NULL,
        created_at TEXT NOT NULL,
        sort_order INTEGER NOT NULL,
        FOREIGN KEY (equipment_id) REFERENCES equipment(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS asset_subsystems (
        id TEXT PRIMARY KEY,
        equipment_id TEXT NOT NULL,
        name TEXT NOT NULL,
        component TEXT NOT NULL,
        condition TEXT NOT NULL,
        detail TEXT NOT NULL,
        sort_order INTEGER NOT NULL,
        FOREIGN KEY (equipment_id) REFERENCES equipment(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS asset_reliability_metrics (
        id TEXT PRIMARY KEY,
        equipment_id TEXT NOT NULL,
        metric_name TEXT NOT NULL,
        value REAL NOT NULL,
        unit TEXT NOT NULL,
        target_value REAL,
        status TEXT NOT NULL,
        trend TEXT NOT NULL,
        detail TEXT NOT NULL,
        sort_order INTEGER NOT NULL,
        FOREIGN KEY (equipment_id) REFERENCES equipment(id)
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
        planning_status TEXT NOT NULL DEFAULT 'unscheduled',
        planned_start TEXT,
        planned_end TEXT,
        outage_window TEXT,
        material_readiness TEXT NOT NULL DEFAULT 'unknown',
        material_blocker_status TEXT NOT NULL DEFAULT 'not_required',
        material_blocker_note TEXT,
        dispatch_notes TEXT,
        dispatched_at TEXT,
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
    CREATE TABLE IF NOT EXISTS work_order_spares (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        work_order_id TEXT NOT NULL,
        spare_id TEXT,
        spare_name TEXT NOT NULL,
        required_qty INTEGER NOT NULL DEFAULT 1,
        reserved_qty INTEGER NOT NULL DEFAULT 0,
        available_qty INTEGER NOT NULL DEFAULT 0,
        reorder_requested INTEGER NOT NULL DEFAULT 0,
        procurement_status TEXT NOT NULL DEFAULT 'not_requested',
        procurement_lead_time_days INTEGER NOT NULL DEFAULT 0,
        expected_available_date TEXT,
        substitute_spare_id TEXT,
        substitute_name TEXT,
        blocker_status TEXT NOT NULL DEFAULT 'not_required',
        blocker_note TEXT,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (work_order_id) REFERENCES work_orders(id),
        FOREIGN KEY (spare_id) REFERENCES spares(id)
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
    CREATE TABLE IF NOT EXISTS rca_cases (
        id TEXT PRIMARY KEY,
        equipment_id TEXT NOT NULL,
        work_order_id TEXT,
        title TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        severity TEXT NOT NULL DEFAULT 'medium',
        problem_statement TEXT NOT NULL,
        symptoms TEXT NOT NULL DEFAULT '[]',
        hypotheses TEXT NOT NULL DEFAULT '[]',
        why_chain TEXT NOT NULL DEFAULT '[]',
        fishbone TEXT NOT NULL DEFAULT '{}',
        evidence_timeline TEXT NOT NULL DEFAULT '[]',
        corrective_actions TEXT NOT NULL DEFAULT '[]',
        closure_review TEXT,
        probable_cause TEXT,
        confidence REAL NOT NULL DEFAULT 0,
        missing_checks TEXT NOT NULL DEFAULT '[]',
        morpheus_summary TEXT,
        morpheus_fishbone_text TEXT,
        used_live_provider INTEGER NOT NULL DEFAULT 0,
        provider TEXT NOT NULL DEFAULT 'mock',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        closed_at TEXT,
        FOREIGN KEY (equipment_id) REFERENCES equipment(id),
        FOREIGN KEY (work_order_id) REFERENCES work_orders(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pm_templates (
        id TEXT PRIMARY KEY,
        equipment_id TEXT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        cadence_days INTEGER NOT NULL DEFAULT 30,
        work_type TEXT NOT NULL DEFAULT 'PM',
        task_list TEXT NOT NULL DEFAULT '[]',
        thresholds TEXT NOT NULL DEFAULT '[]',
        source TEXT NOT NULL DEFAULT 'seed',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (equipment_id) REFERENCES equipment(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pm_plans (
        id TEXT PRIMARY KEY,
        equipment_id TEXT NOT NULL,
        template_id TEXT,
        title TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'draft',
        cadence_days INTEGER NOT NULL DEFAULT 30,
        next_due_date TEXT NOT NULL,
        trigger TEXT NOT NULL DEFAULT '{}',
        thresholds TEXT NOT NULL DEFAULT '[]',
        tasks TEXT NOT NULL DEFAULT '[]',
        smith_steps TEXT NOT NULL DEFAULT '[]',
        spares_strategy TEXT NOT NULL DEFAULT '[]',
        evidence TEXT NOT NULL DEFAULT '[]',
        adjustment_notes TEXT NOT NULL DEFAULT '[]',
        source TEXT NOT NULL DEFAULT 'deterministic',
        generated_by TEXT NOT NULL DEFAULT 'morpheus',
        used_live_provider INTEGER NOT NULL DEFAULT 0,
        provider TEXT NOT NULL DEFAULT 'mock',
        converted_work_order_id TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (equipment_id) REFERENCES equipment(id),
        FOREIGN KEY (template_id) REFERENCES pm_templates(id),
        FOREIGN KEY (converted_work_order_id) REFERENCES work_orders(id)
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
        embedding_profile_id TEXT NOT NULL DEFAULT 'emb-legacy',
        embedding_provider TEXT NOT NULL DEFAULT 'deterministic_hash',
        embedding_model TEXT NOT NULL DEFAULT 'maintenance-hash-v1',
        embedding_version TEXT NOT NULL DEFAULT '1',
        embedding_dimensions INTEGER NOT NULL DEFAULT 64,
        embedding_distance TEXT NOT NULL DEFAULT 'Cosine',
        embedded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (document_id) REFERENCES documents(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rag_embedding_profiles (
        id TEXT PRIMARY KEY,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        version TEXT NOT NULL,
        dimensions INTEGER NOT NULL,
        distance TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'candidate',
        notes TEXT,
        metadata TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(provider, model, version, dimensions, distance)
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
    """
    CREATE TABLE IF NOT EXISTS learning_interactions (
        id TEXT PRIMARY KEY,
        assistant TEXT NOT NULL,
        interaction_type TEXT NOT NULL,
        user_id TEXT,
        user_role TEXT,
        equipment_id TEXT,
        work_order_id TEXT,
        prompt TEXT NOT NULL,
        response TEXT NOT NULL,
        provider TEXT NOT NULL DEFAULT 'mock',
        used_live_provider INTEGER NOT NULL DEFAULT 0,
        prompt_version TEXT NOT NULL DEFAULT 'default',
        model_version TEXT NOT NULL DEFAULT 'default',
        source_refs TEXT NOT NULL DEFAULT '[]',
        approved_for_learning INTEGER NOT NULL DEFAULT 0,
        outcome_status TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS assistant_sessions (
        id TEXT PRIMARY KEY,
        assistant_id TEXT NOT NULL,
        user_id TEXT,
        user_role TEXT,
        screen TEXT,
        status TEXT NOT NULL DEFAULT 'active',
        metadata TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS assistant_messages (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        assistant_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        provider TEXT,
        used_live_provider INTEGER NOT NULL DEFAULT 0,
        tool_calls TEXT NOT NULL DEFAULT '[]',
        tool_results TEXT NOT NULL DEFAULT '[]',
        final_response TEXT,
        metadata TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES assistant_sessions(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS learning_examples (
        id TEXT PRIMARY KEY,
        source_type TEXT NOT NULL,
        source_id TEXT NOT NULL,
        equipment_id TEXT,
        work_order_id TEXT,
        instruction TEXT NOT NULL,
        input_text TEXT NOT NULL,
        expected_output TEXT NOT NULL,
        metadata TEXT NOT NULL DEFAULT '{}',
        approved INTEGER NOT NULL DEFAULT 0,
        judge_score REAL NOT NULL DEFAULT 0,
        judge_label TEXT NOT NULL DEFAULT 'not_scored',
        judge_rationale TEXT,
        judge_provider TEXT NOT NULL DEFAULT 'not_scored',
        judge_used_live_provider INTEGER NOT NULL DEFAULT 0,
        judged_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(source_type, source_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS learning_dataset_snapshots (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        example_count INTEGER NOT NULL,
        approved_only INTEGER NOT NULL DEFAULT 1,
        jsonl_content TEXT NOT NULL,
        created_by TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS learning_model_versions (
        id TEXT PRIMARY KEY,
        provider TEXT NOT NULL,
        model_name TEXT NOT NULL,
        base_model TEXT,
        adapter_path TEXT,
        status TEXT NOT NULL DEFAULT 'candidate',
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS learning_prompt_versions (
        id TEXT PRIMARY KEY,
        assistant TEXT NOT NULL,
        version TEXT NOT NULL,
        prompt TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'candidate',
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(assistant, version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS learning_evaluation_runs (
        id TEXT PRIMARY KEY,
        dataset_id TEXT,
        model_version_id TEXT,
        prompt_version_id TEXT,
        metrics TEXT NOT NULL,
        notes TEXT,
        passed INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS learning_jobs (
        id TEXT PRIMARY KEY,
        job_type TEXT NOT NULL,
        subject TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'queued',
        requested_by TEXT,
        correlation_id TEXT NOT NULL,
        input_refs TEXT NOT NULL DEFAULT '{}',
        output_refs TEXT NOT NULL DEFAULT '{}',
        error TEXT,
        retry_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS learning_artifacts (
        id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL,
        artifact_type TEXT NOT NULL,
        uri TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        metadata TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (job_id) REFERENCES learning_jobs(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS learning_model_promotions (
        id TEXT PRIMARY KEY,
        model_version_id TEXT NOT NULL,
        previous_active_model_id TEXT,
        evaluation_run_id TEXT NOT NULL,
        dataset_id TEXT NOT NULL,
        prompt_version_id TEXT NOT NULL,
        action TEXT NOT NULL,
        reviewer_email TEXT NOT NULL,
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (model_version_id) REFERENCES learning_model_versions(id),
        FOREIGN KEY (evaluation_run_id) REFERENCES learning_evaluation_runs(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS learning_model_deployments (
        id TEXT PRIMARY KEY,
        model_version_id TEXT NOT NULL,
        job_id TEXT,
        runtime_provider TEXT NOT NULL,
        serving_provider TEXT NOT NULL,
        served_model_name TEXT NOT NULL,
        base_url TEXT,
        artifact_uri TEXT,
        artifact_hash TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        health_status TEXT,
        health_checked_at TEXT,
        metadata TEXT NOT NULL DEFAULT '{}',
        error TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (model_version_id) REFERENCES learning_model_versions(id),
        FOREIGN KEY (job_id) REFERENCES learning_jobs(id)
    )
    """,
]

SCHEMA_VERSION = "20"
_INITIALIZING = False


def is_initializing_database() -> bool:
    return _INITIALIZING


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
    global _INITIALIZING
    _INITIALIZING = True
    try:
        with connect() as connection:
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)
            _ensure_column(connection, "feedback", "equipment_id", "TEXT")
            _ensure_column(connection, "learning_examples", "judge_score", "REAL NOT NULL DEFAULT 0")
            _ensure_column(connection, "learning_examples", "judge_label", "TEXT NOT NULL DEFAULT 'not_scored'")
            _ensure_column(connection, "learning_examples", "judge_rationale", "TEXT")
            _ensure_column(connection, "learning_examples", "judge_provider", "TEXT NOT NULL DEFAULT 'not_scored'")
            _ensure_column(connection, "learning_examples", "judge_used_live_provider", "INTEGER NOT NULL DEFAULT 0")
            _ensure_column(connection, "learning_examples", "judged_at", "TEXT")
            _ensure_column(connection, "learning_jobs", "output_refs", "TEXT NOT NULL DEFAULT '{}'")
            _ensure_column(connection, "learning_jobs", "retry_count", "INTEGER NOT NULL DEFAULT 0")
            _ensure_column(connection, "learning_model_deployments", "metadata", "TEXT NOT NULL DEFAULT '{}'")
            _ensure_column(connection, "learning_model_deployments", "error", "TEXT")
            _ensure_column(connection, "document_chunks", "embedding_profile_id", "TEXT NOT NULL DEFAULT 'emb-legacy'")
            _ensure_column(connection, "document_chunks", "embedding_provider", "TEXT NOT NULL DEFAULT 'deterministic_hash'")
            _ensure_column(connection, "document_chunks", "embedding_model", "TEXT NOT NULL DEFAULT 'maintenance-hash-v1'")
            _ensure_column(connection, "document_chunks", "embedding_version", "TEXT NOT NULL DEFAULT '1'")
            _ensure_column(connection, "document_chunks", "embedding_dimensions", "INTEGER NOT NULL DEFAULT 64")
            _ensure_column(connection, "document_chunks", "embedding_distance", "TEXT NOT NULL DEFAULT 'Cosine'")
            _ensure_column(connection, "document_chunks", "embedded_at", "TEXT")
            _ensure_column(connection, "work_orders", "planning_status", "TEXT NOT NULL DEFAULT 'unscheduled'")
            _ensure_column(connection, "work_orders", "planned_start", "TEXT")
            _ensure_column(connection, "work_orders", "planned_end", "TEXT")
            _ensure_column(connection, "work_orders", "outage_window", "TEXT")
            _ensure_column(connection, "work_orders", "material_readiness", "TEXT NOT NULL DEFAULT 'unknown'")
            _ensure_column(connection, "work_orders", "material_blocker_status", "TEXT NOT NULL DEFAULT 'not_required'")
            _ensure_column(connection, "work_orders", "material_blocker_note", "TEXT")
            _ensure_column(connection, "work_orders", "dispatch_notes", "TEXT")
            _ensure_column(connection, "work_orders", "dispatched_at", "TEXT")
            _ensure_column(connection, "rca_cases", "morpheus_fishbone_text", "TEXT")
            _ensure_column(connection, "pm_plans", "smith_steps", "TEXT NOT NULL DEFAULT '[]'")
            _ensure_column(connection, "pm_plans", "converted_work_order_id", "TEXT")
            connection.execute(
                """
                UPDATE document_chunks
                SET embedded_at = CURRENT_TIMESTAMP
                WHERE embedded_at IS NULL
                """
            )
            connection.execute(
                """
                INSERT INTO schema_metadata (key, value)
                VALUES ('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (SCHEMA_VERSION,),
            )
            _seed_learning_defaults(connection)
            _seed_rag_embedding_profile(connection)
            if seed:
                seed_from_sample_data(connection)
                if get_settings().auth_seed_demo_users:
                    _execute_seed_sql(connection, "users_seed.sql")
    finally:
        _INITIALIZING = False


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
    seed_demo_rca_cases(connection)
    seed_demo_pm_templates(connection)
    _execute_seed_sql(connection, "asset_detail_seed.sql")
    from app.data.repository import rebuild_document_chunks

    rebuild_document_chunks(connection)


def seed_demo_work_orders(connection: sqlite3.Connection) -> None:
    work_orders = [
        {
            "id": "WO-8304",
            "equipment_id": "RM-DRIVE-01",
            "title": "Inspect main drive bearing vibration",
            "description": "Inspect drive-end bearing housing, coupling alignment, lubrication condition, and foundation bolts after critical vibration alert.",
            "status": "WMATL",
            "priority": 1,
            "work_type": "CM",
            "failure_class": "MECH",
            "problem_code": "BRGVIB",
            "classification": "Bearing vibration",
            "assigned_to": "Vinoth",
            "supervisor": "Dhruv",
            "due_date": "2026-06-12T18:00:00+05:30",
            "planning_status": "planned",
            "planned_start": "2026-06-12T14:00:00+05:30",
            "planned_end": "2026-06-12T18:00:00+05:30",
            "outage_window": "Finishing stand load-reduction window",
            "material_readiness": "blocked",
            "material_blocker_status": "blocked",
            "material_blocker_note": "Drive end bearing is out of stock; procure replacement or approve temporary load-reduction inspection scope.",
            "dispatch_notes": "Bearing spare availability must be confirmed before intrusive work.",
            "dispatched_at": None,
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
            "status": "WAPPR",
            "priority": 2,
            "work_type": "CM",
            "failure_class": "CTRL",
            "problem_code": "IGVACT",
            "classification": "Control actuator",
            "assigned_to": "Guna",
            "supervisor": "Blast Furnace Supervisor",
            "due_date": "2026-06-13T12:00:00+05:30",
            "planning_status": "unscheduled",
            "planned_start": None,
            "planned_end": None,
            "outage_window": None,
            "material_readiness": "unknown",
            "material_blocker_status": "not_required",
            "material_blocker_note": None,
            "dispatch_notes": None,
            "dispatched_at": None,
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
            "planning_status": "dispatched",
            "planned_start": "2026-06-11T13:30:00+05:30",
            "planned_end": "2026-06-11T16:30:00+05:30",
            "outage_window": "Crane heavy-lift restriction window",
            "material_readiness": "blocked",
            "material_blocker_status": "reorder_requested",
            "material_blocker_note": "Brake shoe replacement follow-up is waiting on procurement confirmation.",
            "dispatch_notes": "Replacement brake shoes require follow-up procurement.",
            "dispatched_at": "2026-06-11T12:45:00+05:30",
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
            "planning_status": "planned",
            "planned_start": "2026-06-14T08:00:00+05:30",
            "planned_end": "2026-06-14T10:00:00+05:30",
            "outage_window": "Morning roll-gap correction maintenance window",
            "material_readiness": "pending",
            "material_blocker_status": "waiting_procurement",
            "material_blocker_note": "Pump cartridge reservation is pending; servo valve seal kit can support a limited inspection.",
            "dispatch_notes": "Pump cartridge assembly reservation is pending.",
            "dispatched_at": None,
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
        "planning_status",
        "planned_start",
        "planned_end",
        "outage_window",
        "material_readiness",
        "material_blocker_status",
        "material_blocker_note",
        "dispatch_notes",
        "dispatched_at",
        "recommended_action",
        "follow_up_required",
        "ai_summary",
        "completion_summary",
        "completed_at",
    ]
    _insert_many(connection, "work_orders", columns, work_orders)
    connection.execute(
        "DELETE FROM work_order_spares WHERE work_order_id IN ('WO-8304', 'WO-8311', 'WO-8297', 'WO-8275')"
    )
    connection.executemany(
        """
        INSERT INTO work_order_spares (
            work_order_id,
            spare_id,
            spare_name,
            required_qty,
            reserved_qty,
            available_qty,
            reorder_requested,
            procurement_status,
            procurement_lead_time_days,
            expected_available_date,
            substitute_spare_id,
            substitute_name,
            blocker_status,
            blocker_note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "WO-8304",
                "SP-001",
                "Drive end spherical roller bearing",
                1,
                0,
                0,
                1,
                "requested",
                21,
                "2026-07-03",
                "SP-002",
                "High-temperature coupling grease for non-intrusive lubrication inspection",
                "blocked",
                "No bearing is available for replacement; substitute supports inspection only, not bearing changeout.",
            ),
            (
                "WO-8311",
                "SP-003",
                "Blower inlet guide vane actuator",
                1,
                0,
                1,
                0,
                "not_requested",
                12,
                None,
                None,
                None,
                "reserved",
                "One actuator is available if stroke testing confirms replacement need.",
            ),
            (
                "WO-8297",
                "SP-006",
                "Main hoist brake shoe set",
                1,
                0,
                0,
                1,
                "requested",
                14,
                "2026-06-25",
                None,
                None,
                "reorder_requested",
                "Procurement request is needed before brake shoe replacement follow-up.",
            ),
            (
                "WO-8275",
                "SP-004",
                "Hydraulic pump cartridge assembly",
                1,
                0,
                0,
                1,
                "ordered",
                18,
                "2026-07-02",
                "SP-005",
                "Servo valve seal kit",
                "waiting_procurement",
                "Pump cartridge is on order; seal kit can support inspection and minor leak correction.",
            ),
        ],
    )
    connection.execute("DELETE FROM work_order_logs WHERE work_order_id IN ('WO-8304', 'WO-8297')")
    connection.executemany(
        """
        INSERT INTO work_order_logs (work_order_id, author, entry_type, content)
        VALUES (?, ?, ?, ?)
        """,
        [
            ("WO-8304", "Maintenance Wizard", "assistant", "Start with lockout, bearing temperature, coupling alignment, and foundation bolt checks."),
            ("WO-8304", "Lokesh", "observation", "Drive-end vibration confirmed at reduced finishing stand load."),
            ("WO-8297", "Crane Technician", "completion", "Brake temperature normalized after restriction; shoe set needs follow-up replacement planning."),
        ],
    )


def seed_demo_rca_cases(connection: sqlite3.Connection) -> None:
    cases = [
        {
            "id": "RCA-9001",
            "equipment_id": "RM-DRIVE-01",
            "work_order_id": "WO-8304",
            "title": "Drive-end vibration root cause review",
            "status": "investigating",
            "severity": "critical",
            "problem_statement": (
                "Critical drive-end vibration continues on the hot strip mill main drive while "
                "the bearing spare is unavailable."
            ),
            "symptoms": [
                "Drive-end vibration exceeded the critical threshold during finishing stand load.",
                "Technician observation reported hotspots and looseness around checked connections.",
                "Bearing replacement is blocked until the drive-end bearing is procured.",
            ],
            "hypotheses": [
                {
                    "id": "HYP-1",
                    "cause": "Drive-end bearing wear or lubrication degradation",
                    "confidence": 0.68,
                    "evidence": ["WO-8304 material blocker", "Prior vibration alert", "Bearing spare shortage"],
                    "missing_checks": ["Confirm bearing temperature trend", "Inspect lubricant condition"],
                    "status": "candidate",
                },
                {
                    "id": "HYP-2",
                    "cause": "Coupling misalignment or foundation bolt looseness under load",
                    "confidence": 0.52,
                    "evidence": ["Reported looseness", "Reduced-load vibration recurrence"],
                    "missing_checks": ["Torque foundation bolts", "Check coupling alignment readings"],
                    "status": "candidate",
                },
            ],
            "why_chain": [
                "Why did vibration exceed threshold? Drive-end rotating assembly is unstable under rolling load.",
                "Why is the assembly unstable? Bearing condition or alignment looseness has not been isolated.",
                "Why has intrusive confirmation not started? The required bearing spare is unavailable.",
            ],
            "fishbone": {
                "Machine": ["Drive-end bearing", "Coupling alignment", "Foundation bolts"],
                "Method": ["Reduced-load inspection only until spare is available"],
                "Material": ["Drive end spherical roller bearing out of stock"],
                "Measurement": ["Vibration trend", "Bearing temperature", "Alignment readings"],
                "Environment": ["Finishing stand high-load campaign"],
            },
            "evidence_timeline": [
                {
                    "id": "EV-1",
                    "timestamp": "2026-06-12T14:00:00+05:30",
                    "source_type": "work_order",
                    "source_id": "WO-8304",
                    "title": "Work order blocked by material",
                    "summary": "Drive end bearing is out of stock; intrusive replacement cannot proceed.",
                    "relevance": "Explains why the RCA must separate safe inspection from corrective repair.",
                },
                {
                    "id": "EV-2",
                    "timestamp": "2026-06-12T15:00:00+05:30",
                    "source_type": "log",
                    "source_id": "WO-8304",
                    "title": "Technician observation",
                    "summary": "Hotspots and looseness were observed around checked connections.",
                    "relevance": "Supports alignment or looseness hypothesis.",
                },
            ],
            "corrective_actions": [
                {
                    "id": "CA-1",
                    "action": "Procure drive-end bearing and reserve installation window.",
                    "owner": "Priya",
                    "due_date": "2026-07-03",
                    "status": "approved",
                    "verification": "Bearing received and reserved against WO-8304.",
                },
                {
                    "id": "CA-2",
                    "action": "Complete non-intrusive temperature, alignment, and bolt torque checks.",
                    "owner": "Lokesh",
                    "due_date": "2026-06-14",
                    "status": "in_progress",
                    "verification": "Attach readings and photos to the RCA evidence timeline.",
                },
            ],
            "closure_review": None,
            "probable_cause": "Drive-end bearing wear or coupling looseness remains probable pending missing checks.",
            "confidence": 0.62,
            "missing_checks": ["Bearing temperature trend", "Lubricant condition", "Coupling alignment", "Foundation bolt torque"],
            "morpheus_summary": "Morpheus should prioritize safe evidence capture until the blocked bearing spare is available.",
            "used_live_provider": 0,
            "provider": "seed",
            "closed_at": None,
        }
    ]
    _insert_many(
        connection,
        "rca_cases",
        [
            "id",
            "equipment_id",
            "work_order_id",
            "title",
            "status",
            "severity",
            "problem_statement",
            "symptoms",
            "hypotheses",
            "why_chain",
            "fishbone",
            "evidence_timeline",
            "corrective_actions",
            "closure_review",
            "probable_cause",
            "confidence",
            "missing_checks",
            "morpheus_summary",
            "morpheus_fishbone_text",
            "used_live_provider",
            "provider",
            "closed_at",
        ],
        cases,
    )


def seed_demo_pm_templates(connection: sqlite3.Connection) -> None:
    templates = [
        {
            "id": "PMT-RM-DRIVE-BEARING",
            "equipment_id": "RM-DRIVE-01",
            "title": "Drive bearing and coupling health PM",
            "description": "Recurring vibration, temperature, lubrication, and coupling inspection for the hot strip mill main drive.",
            "cadence_days": 14,
            "work_type": "PM",
            "task_list": [
                "Trend drive-end vibration against trip advisory threshold.",
                "Measure bearing housing temperature and compare to baseline.",
                "Inspect coupling alignment marks and foundation bolt torque.",
                "Check lubricant condition and contamination indicators.",
            ],
            "thresholds": [
                "drive_end_vibration >= 7.1 mm/s",
                "bearing_temperature above rolling baseline by 10 C",
            ],
            "source": "sop",
        },
        {
            "id": "PMT-HYD-TEMP-PULSATION",
            "equipment_id": "HYD-SYS-04",
            "title": "Hydraulic temperature and pulsation PM",
            "description": "Condition-based hydraulic oil temperature, cooler, pump, and pressure pulsation inspection.",
            "cadence_days": 21,
            "work_type": "PM",
            "task_list": [
                "Inspect cooler differential temperature and cleanliness.",
                "Trend hydraulic oil temperature during roll gap correction.",
                "Check pressure pulsation and pump cartridge condition.",
                "Verify servo valve contamination and seal condition.",
            ],
            "thresholds": [
                "hydraulic_oil_temperature >= 68 C",
                "pressure_pulsation trend increase during AGC correction",
            ],
            "source": "manual",
        },
        {
            "id": "PMT-CRANE-HOIST-BRAKE",
            "equipment_id": "OH-CRANE-05",
            "title": "Hoist brake and motor current PM",
            "description": "Recurring inspection for hoist brake thermal risk and motor current abnormality.",
            "cadence_days": 30,
            "work_type": "PM",
            "task_list": [
                "Trend hoist motor current during heavy lift cycles.",
                "Measure brake shoe temperature after load restriction.",
                "Inspect brake shoe wear and air gap.",
                "Confirm replacement shoe availability before intrusive work.",
            ],
            "thresholds": [
                "hoist_motor_current above current baseline",
                "brake_temperature above safe operating threshold",
            ],
            "source": "history",
        },
    ]
    _insert_many(
        connection,
        "pm_templates",
        [
            "id",
            "equipment_id",
            "title",
            "description",
            "cadence_days",
            "work_type",
            "task_list",
            "thresholds",
            "source",
        ],
        templates,
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
        "asset_profiles",
        "asset_metric_snapshots",
        "asset_recommendations",
        "asset_subsystems",
        "asset_reliability_metrics",
        "alerts",
        "sensor_readings",
        "spares",
        "maintenance_events",
        "work_orders",
        "work_order_spares",
        "work_order_logs",
        "rca_cases",
        "pm_templates",
        "pm_plans",
        "documents",
        "document_chunks",
        "rag_embedding_profiles",
        "document_intelligence",
        "feedback",
        "maintenance_labels",
        "streaming_messages",
        "users",
        "auth_audit_events",
        "learning_interactions",
        "assistant_sessions",
        "assistant_messages",
        "learning_examples",
        "learning_dataset_snapshots",
        "learning_model_versions",
        "learning_prompt_versions",
        "learning_evaluation_runs",
        "learning_jobs",
        "learning_artifacts",
        "learning_model_promotions",
        "learning_model_deployments",
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


def _execute_seed_sql(connection: sqlite3.Connection, filename: str) -> None:
    seed_path = get_settings().data_dir / filename
    if seed_path.exists():
        connection.executescript(seed_path.read_text(encoding="utf-8"))


def _seed_learning_defaults(connection: sqlite3.Connection) -> None:
    settings = get_settings()
    model_name = settings.ollama_model if settings.llm_provider == "ollama" else settings.openai_model
    connection.executemany(
        """
        INSERT INTO learning_model_versions (
            id, provider, model_name, base_model, adapter_path, status, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO NOTHING
        """,
        [
            (
                "model-local-qwen2.5-current",
                settings.llm_provider,
                model_name,
                "qwen2.5-7b-instruct",
                None,
                "active",
                "Current locally configured OpenAI-compatible model endpoint.",
            )
        ],
    )
    connection.executemany(
        """
        INSERT INTO learning_prompt_versions (
            id, assistant, version, prompt, status, notes
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(assistant, version) DO NOTHING
        """,
        [
            (
                "prompt-neo-default",
                "neo",
                "default",
                "Role-aware dashboard assistant prompt with deterministic role and action guards.",
                "active",
                "Used for dashboard, asset, user, and work-order assistance.",
            ),
            (
                "prompt-morpheus-default",
                "morpheus",
                "default",
                "Diagnosis and recommendation prompt grounded in health, work history, and retrieved evidence.",
                "active",
                "Used for streamed diagnosis and recommendation review.",
            ),
            (
                "prompt-smith-default",
                "smith",
                "default",
                "Failure prediction prompt grounded in asset profile, reliability metrics, probability, RUL, and drivers.",
                "active",
                "Used for streamed reliability prediction.",
            ),
        ],
    )


def _seed_rag_embedding_profile(connection: sqlite3.Connection) -> None:
    from app.services.embeddings import settings_embedding_profile

    profile = settings_embedding_profile()
    connection.execute(
        """
        UPDATE rag_embedding_profiles
        SET status = 'candidate',
            updated_at = CURRENT_TIMESTAMP
        WHERE status = 'active'
          AND id <> ?
        """,
        (profile.id,),
    )
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
            status='active',
            notes=excluded.notes,
            metadata=excluded.metadata,
            updated_at=CURRENT_TIMESTAMP
        """,
        (
            profile.id,
            profile.provider,
            profile.model,
            profile.version,
            profile.dimensions,
            profile.distance,
            "active",
            profile.notes,
            json.dumps(profile.metadata or {}, separators=(",", ":")),
        ),
    )
