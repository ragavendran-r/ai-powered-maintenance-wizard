from typing import Any, Optional

from datetime import datetime, timedelta, timezone
import json
import sqlite3
from threading import Lock
import uuid

from app.core.security import hash_password
from app.data.database import connect, initialize_database
from app.services.vector_index import build_chunks_for_document
from app.services.vector_store import (
    delete_plant_records_index,
    index_document_chunks,
    sync_learning_examples_index,
    sync_plant_records_index,
)


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


def list_unseen_alerts(user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT a.*
        FROM alerts a
        LEFT JOIN user_alert_views v
            ON v.alert_id = a.id
            AND v.user_id = ?
        WHERE v.alert_id IS NULL
        ORDER BY
            CASE a.severity
                WHEN 'critical' THEN 4
                WHEN 'high' THEN 3
                WHEN 'medium' THEN 2
                ELSE 1
            END DESC,
            a.timestamp DESC
        LIMIT ?
        """,
        (user_id, limit),
    )


def mark_alert_seen(user_id: str, alert_id: str, dismissed: bool = False) -> Optional[dict[str, Any]]:
    ensure_ready()
    if not _fetch_one("SELECT id FROM alerts WHERE id = ?", (alert_id,)):
        return None
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO user_alert_views (user_id, alert_id, dismissed_at)
            VALUES (?, ?, CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE NULL END)
            ON CONFLICT(user_id, alert_id) DO UPDATE SET
                dismissed_at = CASE
                    WHEN excluded.dismissed_at IS NOT NULL THEN excluded.dismissed_at
                    ELSE user_alert_views.dismissed_at
                END
            """,
            (user_id, alert_id, 1 if dismissed else 0),
        )
    return _fetch_one(
        """
        SELECT user_id, alert_id, first_seen_at, dismissed_at
        FROM user_alert_views
        WHERE user_id = ? AND alert_id = ?
        """,
        (user_id, alert_id),
    )


def create_notification_event(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_ready()
    notification_id = payload.get("id") or f"NTF-{uuid.uuid4().hex[:12].upper()}"
    recipient_roles = _json_dump(payload.get("recipient_roles", []))
    recipient_user_ids = _json_dump(payload.get("recipient_user_ids", []))
    metadata = _json_dump_any(payload.get("metadata", {}))
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO notification_events (
                id,
                event_key,
                event_type,
                severity,
                title,
                summary,
                recommended_action,
                source_type,
                source_id,
                equipment_id,
                work_order_id,
                alert_id,
                recommendation_id,
                actor_user_id,
                actor_display_name,
                recipient_roles,
                recipient_user_ids,
                metadata,
                llm_provider,
                llm_used_live_provider
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_key) DO NOTHING
            """,
            (
                notification_id,
                payload["event_key"],
                payload["event_type"],
                payload.get("severity") or "info",
                payload["title"],
                payload["summary"],
                payload["recommended_action"],
                payload["source_type"],
                payload["source_id"],
                payload.get("equipment_id"),
                payload.get("work_order_id"),
                payload.get("alert_id"),
                payload.get("recommendation_id"),
                payload.get("actor_user_id"),
                payload.get("actor_display_name"),
                recipient_roles,
                recipient_user_ids,
                metadata,
                payload.get("llm_provider") or "mock",
                1 if payload.get("llm_used_live_provider") else 0,
            ),
        )
    event = get_notification_event_by_key(payload["event_key"])
    if not event:
        raise RuntimeError("Notification event was not persisted")
    sync_plant_records_index([_notification_event_plant_record(event)])
    return event


def get_notification_event_by_key(event_key: str) -> Optional[dict[str, Any]]:
    row = _fetch_one("SELECT * FROM notification_events WHERE event_key = ?", (event_key,))
    return _decode_notification_event(row) if row else None


def list_notifications_for_user(
    user_id: str,
    role: str,
    *,
    unseen_only: bool = False,
    include_dismissed: bool = False,
    limit: int = 50,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    source_type: Optional[str] = None,
) -> list[dict[str, Any]]:
    rows = _fetch_all(
        """
        WITH targeted AS (
            SELECT
                n.*,
                v.first_seen_at AS seen_at,
                v.dismissed_at AS dismissed_at,
                CASE WHEN instr(n.recipient_user_ids, ?) > 0 THEN 1 ELSE 0 END AS direct_target,
                CASE
                    WHEN n.event_type = 'work_order_assigned' AND n.work_order_id IS NOT NULL
                    THEN n.event_type || ':' || n.work_order_id || ':' || n.recipient_user_ids
                    ELSE n.id
                END AS display_group_key
            FROM notification_events n
            LEFT JOIN user_notification_views v
                ON v.notification_id = n.id
                AND v.user_id = ?
            WHERE
                (instr(n.recipient_user_ids, ?) > 0 OR instr(n.recipient_roles, ?) > 0)
                AND (? = 0 OR v.notification_id IS NULL)
                AND (? = 1 OR v.dismissed_at IS NULL)
                AND (? IS NULL OR n.event_type = ?)
                AND (? IS NULL OR n.severity = ?)
                AND (? IS NULL OR n.source_type = ?)
        ),
        ranked AS (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    PARTITION BY display_group_key
                    ORDER BY created_at DESC, id DESC
                ) AS display_rank
            FROM targeted
        )
        SELECT *
        FROM ranked
        WHERE display_rank = 1
        ORDER BY
            direct_target DESC,
            CASE severity
                WHEN 'critical' THEN 5
                WHEN 'high' THEN 4
                WHEN 'medium' THEN 3
                WHEN 'low' THEN 2
                ELSE 1
            END DESC,
            created_at DESC
        LIMIT ?
        """,
        (
            f'"{user_id}"',
            user_id,
            f'"{user_id}"',
            f'"{role}"',
            1 if unseen_only else 0,
            1 if include_dismissed else 0,
            event_type,
            event_type,
            severity,
            severity,
            source_type,
            source_type,
            limit,
        ),
    )
    return [_decode_notification_event(row) for row in rows]


def list_all_notification_events(equipment_id: Optional[str] = None) -> list[dict[str, Any]]:
    if equipment_id:
        rows = _fetch_all(
            "SELECT * FROM notification_events WHERE equipment_id = ? ORDER BY created_at DESC",
            (equipment_id,),
        )
    else:
        rows = _fetch_all("SELECT * FROM notification_events ORDER BY created_at DESC")
    return [_decode_notification_event(row) for row in rows]


def cleanup_notification_events(
    *,
    dry_run: bool = True,
    dismissed_retention_days: int = 7,
    delete_superseded_assignments: bool = True,
    delete_dismissed_direct_notifications: bool = True,
) -> dict[str, Any]:
    ensure_ready()
    dismissed_cutoff = datetime.now(timezone.utc) - timedelta(days=dismissed_retention_days)
    candidates_by_id: dict[str, dict[str, Any]] = {}

    if delete_superseded_assignments:
        for candidate in _superseded_assignment_notification_candidates():
            candidates_by_id[candidate["id"]] = candidate

    if delete_dismissed_direct_notifications:
        for candidate in _dismissed_direct_notification_candidates(dismissed_cutoff):
            candidates_by_id[candidate["id"]] = candidate

    candidates = sorted(candidates_by_id.values(), key=lambda item: (item["reason"], item["created_at"], item["id"]))
    deleted_ids: list[str] = []
    vector_index_result: Optional[dict[str, Any]] = None
    if not dry_run and candidates:
        deleted_ids = [candidate["id"] for candidate in candidates]
        with connect() as connection:
            connection.executemany(
                "DELETE FROM user_notification_views WHERE notification_id = ?",
                [(notification_id,) for notification_id in deleted_ids],
            )
            connection.executemany(
                "DELETE FROM notification_events WHERE id = ?",
                [(notification_id,) for notification_id in deleted_ids],
            )
        vector_index_result = delete_plant_records_index(
            [f"notification_event:{notification_id}" for notification_id in deleted_ids]
        )

    return {
        "dry_run": dry_run,
        "dismissed_retention_days": dismissed_retention_days,
        "delete_superseded_assignments": delete_superseded_assignments,
        "delete_dismissed_direct_notifications": delete_dismissed_direct_notifications,
        "candidate_count": len(candidates),
        "deleted_count": len(deleted_ids),
        "candidates": candidates,
        "deleted_ids": deleted_ids,
        "vector_index_result": vector_index_result,
    }


def mark_notification_seen(user_id: str, notification_id: str, dismissed: bool = False) -> Optional[dict[str, Any]]:
    ensure_ready()
    if not _fetch_one("SELECT id FROM notification_events WHERE id = ?", (notification_id,)):
        return None
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO user_notification_views (user_id, notification_id, dismissed_at)
            VALUES (?, ?, CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE NULL END)
            ON CONFLICT(user_id, notification_id) DO UPDATE SET
                dismissed_at = CASE
                    WHEN excluded.dismissed_at IS NOT NULL THEN excluded.dismissed_at
                    ELSE user_notification_views.dismissed_at
                END
            """,
            (user_id, notification_id, 1 if dismissed else 0),
        )
    row = _fetch_one(
        """
        SELECT n.*, v.first_seen_at AS seen_at, v.dismissed_at AS dismissed_at
        FROM notification_events n
        JOIN user_notification_views v
            ON v.notification_id = n.id
            AND v.user_id = ?
        WHERE n.id = ?
        """,
        (user_id, notification_id),
    )
    return _decode_notification_event(row) if row else None


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


def list_recent_sensor_readings(equipment_id: str, limit: int = 100) -> list[dict[str, Any]]:
    rows = _fetch_all(
        """
        SELECT *
        FROM sensor_readings
        WHERE equipment_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (equipment_id, limit),
    )
    return list(reversed(rows))


def get_sensor_reading_by_identity(equipment_id: str, signal: str, timestamp: str) -> Optional[dict[str, Any]]:
    return _fetch_one(
        """
        SELECT *
        FROM sensor_readings
        WHERE equipment_id = ? AND signal = ? AND timestamp = ?
        LIMIT 1
        """,
        (equipment_id, signal, timestamp),
    )


def purge_iot_sensor_readings() -> dict[str, Any]:
    ensure_ready()
    rows = _fetch_all("SELECT id FROM sensor_readings WHERE id LIKE 'SR-IOT-%' ORDER BY id ASC")
    reading_ids = [row["id"] for row in rows]
    if not reading_ids:
        return {"deleted_count": 0, "vector_index_result": delete_plant_records_index([])}
    with connect() as connection:
        connection.executemany("DELETE FROM sensor_readings WHERE id = ?", [(reading_id,) for reading_id in reading_ids])
    return {
        "deleted_count": len(reading_ids),
        "vector_index_result": delete_plant_records_index([f"sensor_reading:{reading_id}" for reading_id in reading_ids]),
    }


def list_maintenance_events(equipment_id: Optional[str] = None) -> list[dict[str, Any]]:
    if equipment_id:
        return _fetch_all("SELECT * FROM maintenance_events WHERE equipment_id = ? ORDER BY date DESC", (equipment_id,))
    return _fetch_all("SELECT * FROM maintenance_events ORDER BY date DESC")


def list_work_orders(
    equipment_id: Optional[str] = None,
    assigned_to: Optional[str] = None,
    follow_up_only: bool = False,
    planning_status: Optional[str] = None,
    open_only: bool = False,
    limit: Optional[int] = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    where_sql, params = _work_order_filter_sql(
        equipment_id=equipment_id,
        assigned_to=assigned_to,
        follow_up_only=follow_up_only,
        planning_status=planning_status,
        open_only=open_only,
    )
    limit_sql = ""
    if limit is not None:
        limit_sql = "LIMIT ? OFFSET ?"
        params.extend([limit, offset])
    rows = _fetch_all(
        f"""
        SELECT * FROM work_orders
        {where_sql}
        ORDER BY priority ASC, due_date ASC, updated_at DESC
        {limit_sql}
        """,
        tuple(params),
    )
    return [_decode_work_order(row, include_logs=False) for row in rows]


def count_work_orders(
    equipment_id: Optional[str] = None,
    assigned_to: Optional[str] = None,
    follow_up_only: bool = False,
    planning_status: Optional[str] = None,
    open_only: bool = False,
) -> int:
    where_sql, params = _work_order_filter_sql(
        equipment_id=equipment_id,
        assigned_to=assigned_to,
        follow_up_only=follow_up_only,
        planning_status=planning_status,
        open_only=open_only,
    )
    row = _fetch_one(f"SELECT COUNT(*) AS total FROM work_orders {where_sql}", tuple(params))
    return int(row["total"] if row else 0)


def _work_order_filter_sql(
    *,
    equipment_id: Optional[str] = None,
    assigned_to: Optional[str] = None,
    follow_up_only: bool = False,
    planning_status: Optional[str] = None,
    open_only: bool = False,
) -> tuple[str, list[Any]]:
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
    if planning_status:
        clauses.append("planning_status = ?")
        params.append(planning_status)
    if open_only:
        clauses.append("status NOT IN ('COMP', 'CLOSE')")
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where_sql, params


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
                planning_status,
                planned_start,
                planned_end,
                outage_window,
                material_readiness,
                material_blocker_status,
                material_blocker_note,
                dispatch_notes,
                dispatched_at,
                recommended_action,
                follow_up_required,
                ai_summary,
                completion_summary,
                completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                payload.get("assigned_to") or "",
                payload.get("supervisor") or "Maintenance Supervisor",
                payload["due_date"],
                payload.get("planning_status") or "unscheduled",
                payload.get("planned_start"),
                payload.get("planned_end"),
                payload.get("outage_window"),
                payload.get("material_readiness") or "unknown",
                payload.get("material_blocker_status") or "not_required",
                payload.get("material_blocker_note"),
                payload.get("dispatch_notes"),
                payload.get("dispatched_at"),
                payload.get("recommended_action") or "Inspect asset and update work log with findings.",
                1 if payload.get("follow_up_required") else 0,
                payload.get("ai_summary"),
                payload.get("completion_summary"),
                payload.get("completed_at"),
            ),
        )
        _replace_work_order_spares(connection, work_order_id, payload.get("spare_reservations", []))
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
    sync_plant_records_index([_work_order_plant_record(work_order)])
    sync_plant_records_index(
        [_work_order_spare_plant_record(item, work_order_id=work_order["id"], equipment_id=work_order["equipment_id"]) for item in work_order.get("spare_reservations", [])]
        + [_work_order_log_plant_record(item, work_order) for item in work_order.get("logs", [])]
    )
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
        "problem_code",
        "failure_class",
        "classification",
        "ai_summary",
        "completion_summary",
    ):
        if field in payload:
            fields.append(f"{field} = ?")
            values.append(payload[field])
    if payload.get("follow_up_required") is not None:
        fields.append("follow_up_required = ?")
        values.append(1 if payload["follow_up_required"] else 0)
    spare_reservations = payload.get("spare_reservations")
    dispatch_requested = payload.get("planning_status") == "dispatched"
    start_requested = payload.get("status") == "INPRG"
    if (dispatch_requested or start_requested) and not existing.get("dispatched_at"):
        fields.append("dispatched_at = CURRENT_TIMESTAMP")
    if start_requested and payload.get("planning_status") is None and existing.get("planning_status") != "dispatched":
        fields.append("planning_status = ?")
        values.append("dispatched")
    if payload.get("status") in {"COMP", "CLOSE"} and not existing.get("completed_at"):
        fields.append("completed_at = CURRENT_TIMESTAMP")
    if not fields and spare_reservations is None:
        return existing
    stale_spare_record_ids = (
        [
            f"work_order_spare:{reservation['id']}"
            for reservation in existing.get("spare_reservations", [])
            if reservation.get("id") is not None
        ]
        if spare_reservations is not None
        else []
    )
    with connect() as connection:
        if fields:
            fields.append("updated_at = CURRENT_TIMESTAMP")
            values.append(work_order_id)
            connection.execute(f"UPDATE work_orders SET {', '.join(fields)} WHERE id = ?", values)
        if spare_reservations is not None:
            _replace_work_order_spares(connection, work_order_id, spare_reservations)
            connection.execute("UPDATE work_orders SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (work_order_id,))
    work_order = get_work_order(work_order_id)
    if work_order:
        sync_plant_records_index([_work_order_plant_record(work_order)])
        if stale_spare_record_ids:
            delete_plant_records_index(stale_spare_record_ids)
        sync_plant_records_index(
            [
                _work_order_spare_plant_record(item, work_order_id=work_order["id"], equipment_id=work_order["equipment_id"])
                for item in work_order.get("spare_reservations", [])
            ]
        )
    return work_order


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
    work_order = get_work_order(work_order_id)
    if work_order:
        sync_plant_records_index([_work_order_plant_record(work_order)])
        sync_plant_records_index([_work_order_log_plant_record(item, work_order) for item in work_order.get("logs", [])])
    return work_order


def list_rca_cases(
    equipment_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if equipment_id:
        clauses.append("equipment_id = ?")
        params.append(equipment_id)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    rows = _fetch_all(
        f"""
        SELECT * FROM rca_cases
        {where_sql}
        ORDER BY
          CASE status WHEN 'open' THEN 0 WHEN 'investigating' THEN 1 WHEN 'actions_defined' THEN 2 ELSE 3 END,
          updated_at DESC
        LIMIT ?
        """,
        tuple(params),
    )
    return [_decode_rca_case(row) for row in rows]


def get_rca_case(case_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one("SELECT * FROM rca_cases WHERE id = ?", (case_id,))
    return _decode_rca_case(row) if row else None


def create_rca_case(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_ready()
    case_id = payload.get("id") or _next_rca_case_id()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO rca_cases (
                id,
                equipment_id,
                work_order_id,
                title,
                status,
                severity,
                problem_statement,
                symptoms,
                hypotheses,
                why_chain,
                fishbone,
                evidence_timeline,
                corrective_actions,
                closure_review,
                probable_cause,
                confidence,
                missing_checks,
                morpheus_summary,
                morpheus_fishbone_text,
                used_live_provider,
                provider,
                closed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                payload["equipment_id"],
                payload.get("work_order_id"),
                payload["title"],
                payload.get("status") or "open",
                payload.get("severity") or "medium",
                payload["problem_statement"],
                _json_dump_any(payload.get("symptoms", [])),
                _json_dump_any(payload.get("hypotheses", [])),
                _json_dump_any(payload.get("why_chain", [])),
                _json_dump_any(payload.get("fishbone", {})),
                _json_dump_any(payload.get("evidence_timeline", [])),
                _json_dump_any(payload.get("corrective_actions", [])),
                _json_dump_any(payload.get("closure_review")) if payload.get("closure_review") is not None else None,
                payload.get("probable_cause"),
                float(payload.get("confidence") or 0),
                _json_dump_any(payload.get("missing_checks", [])),
                payload.get("morpheus_summary"),
                payload.get("morpheus_fishbone_text"),
                1 if payload.get("used_live_provider") else 0,
                payload.get("provider") or "mock",
                payload.get("closed_at"),
            ),
        )
    case = get_rca_case(case_id)
    if not case:
        raise RuntimeError("RCA case was not persisted")
    sync_plant_records_index([_rca_case_plant_record(case)])
    return case


def update_rca_case(case_id: str, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    ensure_ready()
    if not get_rca_case(case_id):
        return None
    json_fields = {
        "symptoms",
        "hypotheses",
        "why_chain",
        "fishbone",
        "evidence_timeline",
        "corrective_actions",
        "missing_checks",
    }
    text_fields = {
        "title",
        "status",
        "severity",
        "problem_statement",
        "probable_cause",
        "morpheus_summary",
        "morpheus_fishbone_text",
        "provider",
        "closed_at",
    }
    fields: list[str] = []
    values: list[Any] = []
    for field in text_fields:
        if field in payload and payload[field] is not None:
            fields.append(f"{field} = ?")
            values.append(payload[field])
    for field in json_fields:
        if field in payload and payload[field] is not None:
            fields.append(f"{field} = ?")
            values.append(_json_dump_any(payload[field]))
    if "closure_review" in payload:
        fields.append("closure_review = ?")
        values.append(_json_dump_any(payload.get("closure_review")) if payload.get("closure_review") is not None else None)
    if "confidence" in payload and payload["confidence"] is not None:
        fields.append("confidence = ?")
        values.append(float(payload["confidence"]))
    if "used_live_provider" in payload and payload["used_live_provider"] is not None:
        fields.append("used_live_provider = ?")
        values.append(1 if payload["used_live_provider"] else 0)
    if payload.get("status") == "closed" and "closed_at" not in payload:
        fields.append("closed_at = CURRENT_TIMESTAMP")
    if not fields:
        return get_rca_case(case_id)
    fields.append("updated_at = CURRENT_TIMESTAMP")
    values.append(case_id)
    with connect() as connection:
        connection.execute(f"UPDATE rca_cases SET {', '.join(fields)} WHERE id = ?", values)
    case = get_rca_case(case_id)
    if case:
        sync_plant_records_index([_rca_case_plant_record(case)])
    return case


def list_pm_templates(equipment_id: Optional[str] = None) -> list[dict[str, Any]]:
    if equipment_id:
        rows = _fetch_all(
            """
            SELECT * FROM pm_templates
            WHERE equipment_id = ? OR equipment_id IS NULL
            ORDER BY equipment_id DESC, title ASC
            """,
            (equipment_id,),
        )
    else:
        rows = _fetch_all("SELECT * FROM pm_templates ORDER BY equipment_id ASC, title ASC")
    return [_decode_pm_template(row) for row in rows]


def get_pm_template(template_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one("SELECT * FROM pm_templates WHERE id = ?", (template_id,))
    return _decode_pm_template(row) if row else None


def list_pm_plans(
    equipment_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: Optional[int] = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    where_sql, params = _pm_plan_filter_sql(equipment_id=equipment_id, status=status)
    limit_sql = ""
    if limit is not None:
        limit_sql = "LIMIT ? OFFSET ?"
        params.extend([limit, offset])
    rows = _fetch_all(
        f"""
        SELECT * FROM pm_plans
        {where_sql}
        ORDER BY
          CASE status WHEN 'draft' THEN 0 WHEN 'active' THEN 1 WHEN 'converted' THEN 2 ELSE 3 END,
          next_due_date ASC,
          updated_at DESC
        {limit_sql}
        """,
        tuple(params),
    )
    return [_decode_pm_plan(row) for row in rows]


def count_pm_plans(equipment_id: Optional[str] = None, status: Optional[str] = None) -> int:
    where_sql, params = _pm_plan_filter_sql(equipment_id=equipment_id, status=status)
    row = _fetch_one(f"SELECT COUNT(*) AS total FROM pm_plans {where_sql}", tuple(params))
    return int(row["total"] if row else 0)


def _pm_plan_filter_sql(equipment_id: Optional[str] = None, status: Optional[str] = None) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if equipment_id:
        clauses.append("equipment_id = ?")
        params.append(equipment_id)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where_sql, params


def get_pm_plan(plan_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one("SELECT * FROM pm_plans WHERE id = ?", (plan_id,))
    return _decode_pm_plan(row) if row else None


def save_pm_plan(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_ready()
    plan_id = payload.get("id") or _next_pm_plan_id()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO pm_plans (
                id,
                equipment_id,
                template_id,
                title,
                status,
                cadence_days,
                next_due_date,
                trigger,
                thresholds,
                tasks,
                smith_steps,
                spares_strategy,
                evidence,
                adjustment_notes,
                source,
                generated_by,
                used_live_provider,
                provider,
                converted_work_order_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                equipment_id=excluded.equipment_id,
                template_id=excluded.template_id,
                title=excluded.title,
                status=excluded.status,
                cadence_days=excluded.cadence_days,
                next_due_date=excluded.next_due_date,
                trigger=excluded.trigger,
                thresholds=excluded.thresholds,
                tasks=excluded.tasks,
                smith_steps=excluded.smith_steps,
                spares_strategy=excluded.spares_strategy,
                evidence=excluded.evidence,
                adjustment_notes=excluded.adjustment_notes,
                source=excluded.source,
                generated_by=excluded.generated_by,
                used_live_provider=excluded.used_live_provider,
                provider=excluded.provider,
                converted_work_order_id=excluded.converted_work_order_id,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                plan_id,
                payload["equipment_id"],
                payload.get("template_id"),
                payload["title"],
                payload.get("status") or "draft",
                int(payload.get("cadence_days") or 30),
                payload["next_due_date"],
                _json_dump_any(payload.get("trigger", {})),
                _json_dump_any(payload.get("thresholds", [])),
                _json_dump_any(payload.get("tasks", [])),
                _json_dump_any(payload.get("smith_steps", [])),
                _json_dump_any(payload.get("spares_strategy", [])),
                _json_dump_any(payload.get("evidence", [])),
                _json_dump_any(payload.get("adjustment_notes", [])),
                payload.get("source") or "deterministic",
                payload.get("generated_by") or "morpheus",
                1 if payload.get("used_live_provider") else 0,
                payload.get("provider") or "mock",
                payload.get("converted_work_order_id"),
            ),
        )
    plan = get_pm_plan(plan_id)
    if not plan:
        raise RuntimeError("PM plan was not persisted")
    sync_plant_records_index([_pm_plan_plant_record(plan)])
    return plan


def mark_pm_plan_converted(plan_id: str, work_order_id: str) -> Optional[dict[str, Any]]:
    ensure_ready()
    with connect() as connection:
        connection.execute(
            """
            UPDATE pm_plans
            SET status = 'converted',
                converted_work_order_id = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (work_order_id, plan_id),
        )
    plan = get_pm_plan(plan_id)
    if plan:
        sync_plant_records_index([_pm_plan_plant_record(plan)])
    return plan


def _replace_work_order_spares(
    connection: sqlite3.Connection,
    work_order_id: str,
    reservations: list[dict[str, Any]],
) -> None:
    connection.execute("DELETE FROM work_order_spares WHERE work_order_id = ?", (work_order_id,))
    if not reservations:
        return
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
                work_order_id,
                reservation.get("spare_id"),
                reservation["spare_name"],
                int(reservation.get("required_qty") or 0),
                int(reservation.get("reserved_qty") or 0),
                int(reservation.get("available_qty") or 0),
                1 if reservation.get("reorder_requested") else 0,
                reservation.get("procurement_status") or "not_requested",
                int(reservation.get("procurement_lead_time_days") or 0),
                reservation.get("expected_available_date"),
                reservation.get("substitute_spare_id"),
                reservation.get("substitute_name"),
                reservation.get("blocker_status") or "not_required",
                reservation.get("blocker_note"),
            )
            for reservation in reservations
            if str(reservation.get("spare_name", "")).strip()
        ],
    )


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
    plant_records = list_plant_rag_records()
    plant_index_result = sync_plant_records_index(
        plant_records,
        collection_name=collection_name,
    )
    return {
        "document_count": len(documents),
        "chunk_count": len(chunk_rows),
        "index_result": index_result,
        "learning_example_count": len(learning_examples),
        "learning_index_result": learning_index_result,
        "plant_record_count": len(plant_records),
        "plant_index_result": plant_index_result,
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
    persisted_ids = {document["id"] for document in documents}
    persisted = [item for item in list_documents() if item["id"] in persisted_ids]
    if persisted:
        sync_plant_records_index([_document_plant_record(item) for item in persisted])
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
    intelligence = get_document_intelligence(payload["document_id"])
    if intelligence:
        sync_plant_records_index([_document_intelligence_plant_record(intelligence)])


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


def get_document_intelligence(document_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one("SELECT * FROM document_intelligence WHERE document_id = ?", (document_id,))
    return _decode_document_intelligence(row) if row else None


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
        "work_order_spares": [
            "id",
            "work_order_id",
            "spare_id",
            "spare_name",
            "required_qty",
            "reserved_qty",
            "available_qty",
            "reorder_requested",
            "procurement_status",
            "procurement_lead_time_days",
            "expected_available_date",
            "substitute_spare_id",
            "substitute_name",
            "blocker_status",
            "blocker_note",
        ],
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
        ],
    }
    table_defaults = {
        "work_orders": {
            "planning_status": "unscheduled",
            "material_readiness": "unknown",
            "material_blocker_status": "not_required",
        },
        "work_order_spares": {
            "required_qty": 1,
            "reserved_qty": 0,
            "available_qty": 0,
            "reorder_requested": 0,
            "procurement_status": "not_requested",
            "procurement_lead_time_days": 0,
            "blocker_status": "not_required",
        },
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
                [
                    [
                        row[column]
                        if row.get(column) is not None
                        else table_defaults.get(table, {}).get(column)
                        for column in columns
                    ]
                    for row in rows
                ],
            )
            counts[table] = len(rows)
    plant_records = plant_rag_records_from_payload(payload)
    if plant_records:
        sync_plant_records_index(plant_records)
    return counts


def plant_rag_records_from_payload(payload: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for equipment in payload.get("equipment", []):
        records.append(_equipment_plant_record(equipment))
    for alert in payload.get("alerts", []):
        records.append(_alert_plant_record(alert))
    for reading in payload.get("sensor_readings", []):
        records.append(_sensor_reading_plant_record(reading))
    for spare in payload.get("spares", []):
        records.append(_spare_plant_record(spare))
    for work_order in payload.get("work_orders", []):
        records.append(_work_order_plant_record(work_order))
    for reservation in payload.get("work_order_spares", []):
        records.append(_work_order_spare_plant_record(reservation))
    for event in payload.get("maintenance_events", []):
        records.append(_maintenance_event_plant_record(event))
    return [record for record in records if record.get("id") and record.get("content")]


def list_plant_rag_records(equipment_id: Optional[str] = None) -> list[dict[str, Any]]:
    ensure_ready()
    records: list[dict[str, Any]] = []
    equipment_rows = [get_equipment(equipment_id)] if equipment_id else list_equipment()
    for equipment in [item for item in equipment_rows if item]:
        records.append(_equipment_plant_record(equipment))
        profile = get_asset_profile(equipment["id"])
        if profile:
            records.append(_asset_profile_plant_record(profile))
        for snapshot in list_asset_metric_snapshots(equipment["id"]):
            records.append(_asset_metric_snapshot_plant_record(snapshot))
        for recommendation in list_asset_recommendations(equipment["id"]):
            records.append(_asset_recommendation_plant_record(recommendation))
        for subsystem in list_asset_subsystems(equipment["id"]):
            records.append(_asset_subsystem_plant_record(subsystem))
        for metric in list_asset_reliability_metrics(equipment["id"]):
            records.append(_asset_reliability_metric_plant_record(metric))
    for alert in list_alerts(equipment_id):
        records.append(_alert_plant_record(alert))
    for notification in list_all_notification_events(equipment_id=equipment_id):
        records.append(_notification_event_plant_record(notification))
    sensor_rows = list_sensor_readings(equipment_id)
    for reading in sensor_rows[-200:]:
        records.append(_sensor_reading_plant_record(reading))
    if equipment_id:
        for spare in list_spares(equipment_id):
            records.append(_spare_plant_record(spare))
    else:
        for equipment in list_equipment():
            for spare in list_spares(equipment["id"]):
                records.append(_spare_plant_record(spare))
    for work_order in list_work_orders():
        if equipment_id and work_order["equipment_id"] != equipment_id:
            continue
        records.append(_work_order_plant_record(work_order))
        for reservation in work_order.get("spare_reservations", []):
            records.append(_work_order_spare_plant_record(reservation, work_order_id=work_order["id"], equipment_id=work_order["equipment_id"]))
        for log in get_work_order(work_order["id"]).get("logs", []):
            records.append(_work_order_log_plant_record(log, work_order))
    for event in list_maintenance_events(equipment_id):
        records.append(_maintenance_event_plant_record(event))
    for template in list_pm_templates(equipment_id):
        records.append(_pm_template_plant_record(template))
    for plan in list_pm_plans(equipment_id=equipment_id, limit=1000):
        records.append(_pm_plan_plant_record(plan))
    for case in list_rca_cases(equipment_id=equipment_id, limit=1000):
        records.append(_rca_case_plant_record(case))
    for feedback in list_feedback(equipment_id):
        records.append(_feedback_plant_record(feedback))
    for label in list_maintenance_labels(equipment_id):
        records.append(_maintenance_label_plant_record(label))
    for interaction in list_learning_interactions(equipment_id=equipment_id, limit=1000):
        records.append(_interaction_plant_record(interaction))
    for example in list_learning_examples(equipment_id=equipment_id, limit=1000):
        records.append(_learning_example_plant_record(example))
    for document in list_documents(equipment_id):
        records.append(_document_plant_record(document))
    for intelligence in list_document_intelligence(equipment_id):
        records.append(_document_intelligence_plant_record(intelligence))
    if not equipment_id:
        for message in _fetch_all("SELECT * FROM streaming_messages ORDER BY received_at DESC LIMIT 1000"):
            records.append(_streaming_message_plant_record(message))
        for user in list_users():
            records.append(_user_plant_record(user))
        for event in _fetch_all("SELECT * FROM auth_audit_events ORDER BY created_at DESC LIMIT 1000"):
            records.append(_auth_audit_event_plant_record(event))
        for snapshot in list_learning_dataset_snapshots(limit=1000):
            records.append(_learning_snapshot_plant_record(snapshot))
        for model in list_learning_model_versions():
            records.append(_learning_model_version_plant_record(model))
        for prompt in list_learning_prompt_versions():
            records.append(_learning_prompt_version_plant_record(prompt))
        for evaluation in list_learning_evaluation_runs(limit=1000):
            records.append(_learning_evaluation_plant_record(evaluation))
        for promotion in list_learning_model_promotions(limit=1000):
            records.append(_learning_promotion_plant_record(promotion))
        for deployment in list_learning_model_deployments(limit=1000):
            records.append(_learning_deployment_plant_record(deployment))
        for job in list_learning_jobs(limit=1000):
            records.append(_learning_job_plant_record(job))
        for profile in list_rag_embedding_profiles():
            records.append(_rag_embedding_profile_plant_record(profile))
        for artifact in list_learning_artifacts(limit=1000):
            records.append(_learning_artifact_plant_record(artifact))
    return [record for record in records if record.get("id") and record.get("content")]


def _equipment_plant_record(equipment: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"equipment:{equipment['id']}",
        "source_type": "equipment",
        "equipment_id": equipment["id"],
        "title": f"Equipment {equipment['id']} {equipment['name']}",
        "content": (
            f"Equipment {equipment['id']} {equipment['name']} is in {equipment['area']} for {equipment['process']}. "
            f"Criticality {equipment['criticality']}; status {equipment['status']}."
        ),
    }


def _asset_profile_plant_record(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"asset_profile:{profile['equipment_id']}",
        "source_type": "asset_profile",
        "equipment_id": profile["equipment_id"],
        "title": f"Asset profile {profile['equipment_id']} {profile.get('name', '')}".strip(),
        "timestamp": profile.get("last_updated"),
        "content": (
            f"Asset profile for {profile['equipment_id']}: {profile.get('description')}. "
            f"Type {profile.get('asset_type')}; location {profile.get('location_code')} {profile.get('location_name')}; "
            f"system {profile.get('parent_system')}; manufacturer {profile.get('manufacturer')}; model {profile.get('model')}; "
            f"serial {profile.get('serial_number')}; owner {profile.get('owner_team')}; supervisor {profile.get('supervisor')}."
        ),
    }


def _asset_metric_snapshot_plant_record(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"asset_metric_snapshot:{snapshot['id']}",
        "source_type": "asset_metric_snapshot",
        "equipment_id": snapshot["equipment_id"],
        "title": f"Asset metric {snapshot['label']} for {snapshot['equipment_id']}",
        "timestamp": snapshot.get("captured_at"),
        "content": (
            f"Asset metric snapshot {snapshot['id']} for {snapshot['equipment_id']}: {snapshot['label']} "
            f"is {snapshot['value']} {snapshot['unit']} with status {snapshot['status']} and trend {snapshot['trend']}. "
            f"Target {snapshot.get('target_value')}. Detail: {snapshot.get('detail')}."
        ),
    }


def _asset_recommendation_plant_record(recommendation: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"asset_recommendation:{recommendation['id']}",
        "source_type": "asset_recommendation",
        "equipment_id": recommendation["equipment_id"],
        "title": f"Asset recommendation {recommendation['title']}",
        "timestamp": recommendation.get("created_at"),
        "content": (
            f"Asset recommendation {recommendation['id']} for {recommendation['equipment_id']}: "
            f"{recommendation['title']}. Priority {recommendation['priority']}; action type {recommendation['action_type']}; "
            f"source {recommendation['source']}. Description: {recommendation['description']}."
        ),
    }


def _asset_subsystem_plant_record(subsystem: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"asset_subsystem:{subsystem['id']}",
        "source_type": "asset_subsystem",
        "equipment_id": subsystem["equipment_id"],
        "title": f"Asset subsystem {subsystem['name']} for {subsystem['equipment_id']}",
        "content": (
            f"Asset subsystem {subsystem['id']} for {subsystem['equipment_id']}: {subsystem['name']} "
            f"component {subsystem['component']} condition {subsystem['condition']}. Detail: {subsystem['detail']}."
        ),
    }


def _asset_reliability_metric_plant_record(metric: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"asset_reliability_metric:{metric['id']}",
        "source_type": "asset_reliability_metric",
        "equipment_id": metric["equipment_id"],
        "title": f"Reliability metric {metric['metric_name']} for {metric['equipment_id']}",
        "content": (
            f"Reliability metric {metric['id']} for {metric['equipment_id']}: {metric['metric_name']} "
            f"is {metric['value']} {metric['unit']} with status {metric['status']} and trend {metric['trend']}. "
            f"Target {metric.get('target_value')}. Detail: {metric['detail']}."
        ),
    }


def _alert_plant_record(alert: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"alert:{alert['id']}",
        "source_type": "alert",
        "equipment_id": alert["equipment_id"],
        "title": f"{alert['severity'].title()} alert {alert['id']} on {alert['equipment_id']}",
        "timestamp": alert.get("timestamp"),
        "content": (
            f"{alert['severity'].title()} active alert {alert['id']} for {alert['equipment_id']} at {alert.get('timestamp')}: "
            f"{alert.get('message')}. Signal {alert['signal']} value {alert['value']} {alert['unit']} "
            f"against threshold {alert['threshold']}."
        ),
    }


def _notification_event_plant_record(notification: dict[str, Any]) -> dict[str, Any]:
    source_bits = [
        f"source {notification.get('source_type')}:{notification.get('source_id')}",
        f"event {notification.get('event_type')}",
    ]
    if notification.get("work_order_id"):
        source_bits.append(f"work order {notification['work_order_id']}")
    if notification.get("alert_id"):
        source_bits.append(f"alert {notification['alert_id']}")
    return {
        "id": f"notification_event:{notification['id']}",
        "source_type": "notification_event",
        "equipment_id": notification.get("equipment_id"),
        "title": f"{notification['severity'].title()} notification {notification['title']}",
        "timestamp": notification.get("created_at"),
        "content": (
            f"Role notification {notification['id']} for {', '.join(source_bits)}. "
            f"Title: {notification.get('title')}. Summary: {notification.get('summary')}. "
            f"Recommended action: {notification.get('recommended_action')}. "
            f"Recipients roles {', '.join(notification.get('recipient_roles') or [])}; "
            f"recipient users {', '.join(notification.get('recipient_user_ids') or [])}."
        ),
    }


def _sensor_reading_plant_record(reading: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"sensor_reading:{reading['id']}",
        "source_type": "sensor_reading",
        "equipment_id": reading["equipment_id"],
        "title": f"Sensor reading {reading['signal']} on {reading['equipment_id']}",
        "timestamp": reading.get("timestamp"),
        "content": (
            f"Sensor reading {reading['id']} for {reading['equipment_id']} at {reading.get('timestamp')}: "
            f"{reading['signal']} measured {reading['value']} {reading['unit']} against threshold {reading['threshold']}."
        ),
    }


def _spare_plant_record(spare: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"spare:{spare['id']}",
        "source_type": "spare",
        "equipment_id": spare["equipment_id"],
        "title": f"Spare {spare['name']} for {spare['equipment_id']}",
        "content": (
            f"Spare {spare['id']} {spare['name']} supports {spare['equipment_id']}. "
            f"Available quantity {spare['available_qty']}; lead time {spare['lead_time_days']} days; criticality {spare['criticality']}."
        ),
    }


def _work_order_plant_record(work_order: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"work_order:{work_order['id']}",
        "source_type": "work_order",
        "equipment_id": work_order["equipment_id"],
        "title": f"Work order {work_order['id']} {work_order['title']}",
        "timestamp": work_order.get("updated_at") or work_order.get("created_at"),
        "content": (
            f"Work order {work_order['id']} for {work_order['equipment_id']}: {work_order['title']}. "
            f"Status {work_order.get('status')}; priority {work_order.get('priority')}; type {work_order.get('work_type')}; "
            f"material readiness {work_order.get('material_readiness')}; blocker {work_order.get('material_blocker_status')}. "
            f"Description: {work_order.get('description')}. Recommended action: {work_order.get('recommended_action')}."
        ),
    }


def _work_order_spare_plant_record(
    reservation: dict[str, Any],
    work_order_id: Optional[str] = None,
    equipment_id: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "id": f"work_order_spare:{reservation['id']}",
        "source_type": "work_order_spare",
        "equipment_id": equipment_id,
        "title": f"Work order spare {reservation.get('spare_name') or reservation.get('spare_id')}",
        "content": (
            f"Work order spare reservation {reservation['id']} for work order {work_order_id or reservation.get('work_order_id')}: "
            f"{reservation.get('spare_name') or reservation.get('spare_id')} requires {reservation.get('required_qty')} and has "
            f"{reservation.get('available_qty')} available, {reservation.get('reserved_qty')} reserved. "
            f"Procurement status {reservation.get('procurement_status')}; expected availability {reservation.get('expected_available_date')}; "
            f"blocker {reservation.get('blocker_status')} {reservation.get('blocker_note') or ''}."
        ),
    }


def _work_order_log_plant_record(log: dict[str, Any], work_order: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"work_order_log:{log['id']}",
        "source_type": "work_order_log",
        "equipment_id": work_order["equipment_id"],
        "title": f"Work order log {work_order['id']} {log['entry_type']}",
        "timestamp": log.get("created_at"),
        "content": (
            f"Work order log for {work_order['id']} on {work_order['equipment_id']} by {log.get('author')} "
            f"at {log.get('created_at')}: {log.get('entry_type')} - {log.get('content')}."
        ),
    }


def _maintenance_event_plant_record(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"maintenance_event:{event['id']}",
        "source_type": "maintenance_event",
        "equipment_id": event["equipment_id"],
        "title": f"Maintenance event {event['issue']}",
        "timestamp": event.get("date"),
        "content": (
            f"Maintenance event {event['id']} for {event['equipment_id']} on {event.get('date')}: {event['issue']}. "
            f"Root cause: {event.get('root_cause')}. Action: {event.get('action')}. Downtime {event.get('downtime_hours')} hours."
        ),
    }


def _pm_template_plant_record(template: dict[str, Any]) -> dict[str, Any]:
    tasks = "; ".join(str(item) for item in template.get("task_list", [])[:5])
    thresholds = "; ".join(str(item) for item in template.get("thresholds", [])[:5])
    return {
        "id": f"pm_template:{template['id']}",
        "source_type": "pm_template",
        "equipment_id": template.get("equipment_id"),
        "title": f"PM template {template['id']} {template['title']}",
        "timestamp": template.get("updated_at") or template.get("created_at"),
        "content": (
            f"PM template {template['id']}: {template['title']}. Equipment {template.get('equipment_id') or 'generic'}; "
            f"description {template.get('description')}; cadence {template.get('cadence_days')} days; "
            f"work type {template.get('work_type')}; source {template.get('source')}. "
            f"Tasks: {tasks or 'not specified'}. Thresholds: {thresholds or 'not specified'}."
        ),
    }


def _pm_plan_plant_record(plan: dict[str, Any]) -> dict[str, Any]:
    tasks = "; ".join(task.get("description", "") for task in plan.get("tasks", [])[:5])
    thresholds = "; ".join(str(item) for item in plan.get("thresholds", [])[:5])
    return {
        "id": f"pm_plan:{plan['id']}",
        "source_type": "pm_plan",
        "equipment_id": plan["equipment_id"],
        "title": f"PM plan {plan['id']} {plan['title']}",
        "timestamp": plan.get("updated_at") or plan.get("created_at"),
        "content": (
            f"Preventive maintenance plan {plan['id']} for {plan['equipment_id']}: {plan['title']}. "
            f"Status {plan.get('status')}; cadence {plan.get('cadence_days')} days; next due {plan.get('next_due_date')}; "
            f"converted work order {plan.get('converted_work_order_id') or 'none'}. "
            f"Trigger: {plan.get('trigger', {}).get('description') if isinstance(plan.get('trigger'), dict) else plan.get('trigger')}. "
            f"Thresholds: {thresholds or 'not specified'}. Tasks: {tasks or 'not specified'}."
        ),
    }


def _rca_case_plant_record(case: dict[str, Any]) -> dict[str, Any]:
    corrective_actions = "; ".join(str(item) for item in case.get("corrective_actions", [])[:5])
    evidence = "; ".join(str(item) for item in case.get("evidence", [])[:5])
    return {
        "id": f"rca_case:{case['id']}",
        "source_type": "rca_case",
        "equipment_id": case["equipment_id"],
        "title": f"RCA case {case['id']} {case['title']}",
        "timestamp": case.get("updated_at") or case.get("created_at"),
        "content": (
            f"RCA case {case['id']} for {case['equipment_id']}: {case['title']}. "
            f"Status {case.get('status')}; related work order {case.get('work_order_id') or 'none'}. "
            f"Problem statement: {case.get('problem_statement')}. Probable cause: {case.get('probable_cause')}. "
            f"Evidence: {evidence or 'not specified'}. Corrective actions: {corrective_actions or 'not specified'}."
        ),
    }


def _feedback_plant_record(feedback: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"feedback:{feedback['id']}",
        "source_type": "feedback",
        "equipment_id": feedback.get("equipment_id"),
        "title": f"Engineer feedback {feedback['recommendation_id']}",
        "timestamp": feedback.get("created_at"),
        "content": (
            f"Engineer feedback {feedback['id']} for recommendation {feedback['recommendation_id']} on "
            f"{feedback.get('equipment_id') or 'general equipment'}: status {feedback.get('status')}. "
            f"Corrected diagnosis: {feedback.get('corrected_diagnosis') or 'not provided'}. "
            f"Actual root cause: {feedback.get('actual_root_cause') or 'not provided'}. "
            f"Action taken: {feedback.get('action_taken') or 'not provided'}. "
            f"Outcome: {feedback.get('outcome') or 'not provided'}. Notes: {feedback.get('notes') or 'none'}."
        ),
    }


def _maintenance_label_plant_record(label: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"maintenance_label:{label['id']}",
        "source_type": "maintenance_label",
        "equipment_id": label.get("equipment_id"),
        "title": f"Maintenance label {label['source_type']} {label['source_id']}",
        "timestamp": label.get("created_at"),
        "content": (
            f"Maintenance label {label['id']} from {label['source_type']} {label['source_id']} for "
            f"{label.get('equipment_id') or 'general equipment'}: failure mode {label.get('failure_mode')}; "
            f"component {label.get('component')}; root cause {label.get('root_cause')}; action class {label.get('action_class')}; "
            f"outcome {label.get('outcome_status')}; signal hints {', '.join(label.get('signal_hints') or [])}; "
            f"usable for training {label.get('usable_for_training')}; provider {label.get('provider')}."
        ),
    }


def _interaction_plant_record(interaction: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"interaction:{interaction['id']}",
        "source_type": "assistant_interaction",
        "equipment_id": interaction.get("equipment_id"),
        "title": f"{interaction.get('assistant', 'assistant')} {interaction.get('interaction_type', 'interaction')}",
        "timestamp": interaction.get("created_at"),
        "content": (
            f"Assistant interaction {interaction['id']} by {interaction.get('assistant')} for role {interaction.get('user_role')}. "
            f"Type {interaction.get('interaction_type')}; work order {interaction.get('work_order_id') or 'none'}; "
            f"equipment {interaction.get('equipment_id') or 'none'}; provider {interaction.get('provider')}. "
            f"Prompt: {interaction.get('prompt')}. Response: {interaction.get('response')}. "
            f"Outcome: {interaction.get('outcome_status') or 'not recorded'}."
        ),
    }


def _learning_example_plant_record(example: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"learning_example:{example['id']}",
        "source_type": "learning_example",
        "equipment_id": example.get("equipment_id"),
        "title": f"Learning example {example['source_type']} {example['source_id']}",
        "timestamp": example.get("created_at"),
        "content": (
            f"Learning example {example['id']} from {example['source_type']} {example['source_id']} for "
            f"{example.get('equipment_id') or 'general equipment'} and work order {example.get('work_order_id') or 'none'}. "
            f"Approved {example.get('approved')}; judge score {example.get('judge_score')}; label {example.get('judge_label')}; "
            f"rationale {example.get('judge_rationale') or 'not scored'}. Instruction: {example.get('instruction')}. "
            f"Input: {example.get('input_text')}. Expected output: {example.get('expected_output')}."
        ),
    }


def _document_plant_record(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"document:{document['id']}",
        "source_type": "document",
        "equipment_id": document.get("equipment_id"),
        "title": f"Document {document['id']} {document['title']}",
        "content": (
            f"Document {document['id']}: {document.get('title')} from source type {document.get('source_type')} "
            f"for equipment {document.get('equipment_id') or 'general plant context'}. "
            f"Content excerpt: {(document.get('content') or '')[:600]}."
        ),
    }


def _document_intelligence_plant_record(intelligence: dict[str, Any]) -> dict[str, Any]:
    asset_ids = intelligence.get("asset_ids") or []
    equipment_id = asset_ids[0] if len(asset_ids) == 1 else None
    return {
        "id": f"document_intelligence:{intelligence['document_id']}",
        "source_type": "document_intelligence",
        "equipment_id": equipment_id,
        "title": f"Document intelligence {intelligence['document_id']}",
        "timestamp": intelligence.get("created_at"),
        "content": (
            f"Document intelligence for {intelligence['document_id']}: {intelligence.get('summary')}. "
            f"Assets: {', '.join(asset_ids) or 'none'}. Components: {', '.join(intelligence.get('components') or [])}. "
            f"Failure modes: {', '.join(intelligence.get('failure_modes') or [])}. "
            f"Symptoms: {', '.join(intelligence.get('symptoms') or [])}. "
            f"Safety constraints: {', '.join(intelligence.get('safety_constraints') or [])}. "
            f"Spares: {', '.join(intelligence.get('spares') or [])}. Thresholds: {', '.join(intelligence.get('thresholds') or [])}."
        ),
    }


def _streaming_message_plant_record(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"streaming_message:{message['message_id']}",
        "source_type": "streaming_message",
        "equipment_id": None,
        "title": f"Streaming message {message['message_id']}",
        "timestamp": message.get("received_at"),
        "content": (
            f"IoT streaming message audit {message['message_id']} from {message.get('source')}: "
            f"type {message.get('message_type')}; subject {message.get('subject') or 'none'}; "
            f"status {message.get('status')}; error {message.get('error') or 'none'}."
        ),
    }


def _user_plant_record(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"user:{user['id']}",
        "source_type": "user",
        "equipment_id": None,
        "title": f"User {user['display_name']} {user['role']}",
        "timestamp": user.get("updated_at") or user.get("created_at"),
        "content": (
            f"Application user {user['id']} {user.get('display_name')} has role {user.get('role')}; "
            f"email {user.get('email')}; active {user.get('is_active')}; last login {user.get('last_login_at') or 'never'}."
        ),
    }


def _auth_audit_event_plant_record(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"auth_audit_event:{event['id']}",
        "source_type": "auth_audit_event",
        "equipment_id": None,
        "title": f"Auth audit {event['event_type']} {event['id']}",
        "timestamp": event.get("created_at"),
        "content": (
            f"Authentication audit event {event['id']}: type {event.get('event_type')}; "
            f"user {event.get('user_id') or 'unknown'}; email {event.get('email') or 'unknown'}; "
            f"role {event.get('role') or 'unknown'}; success {bool(event.get('success'))}; detail {event.get('detail') or 'none'}."
        ),
    }


def _learning_snapshot_plant_record(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"learning_dataset_snapshot:{snapshot['id']}",
        "source_type": "learning_dataset_snapshot",
        "equipment_id": None,
        "title": f"Learning dataset snapshot {snapshot['name']}",
        "timestamp": snapshot.get("created_at"),
        "content": (
            f"Learning dataset snapshot {snapshot['id']} named {snapshot.get('name')}: "
            f"{snapshot.get('description') or 'no description'}. Example count {snapshot.get('example_count')}; "
            f"approved only {snapshot.get('approved_only')}; created by {snapshot.get('created_by') or 'unknown'}."
        ),
    }


def _learning_model_version_plant_record(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"learning_model_version:{model['id']}",
        "source_type": "learning_model_version",
        "equipment_id": None,
        "title": f"Learning adapter/model version {model['id']}",
        "timestamp": model.get("created_at"),
        "content": (
            f"Learning model or adapter registry entry {model['id']}: provider {model.get('provider')}; "
            f"name {model.get('model_name')}; base model {model.get('base_model') or 'unknown'}; "
            f"adapter path {model.get('adapter_path') or 'none'}; status {model.get('status')}; notes {model.get('notes') or 'none'}."
        ),
    }


def _learning_prompt_version_plant_record(prompt: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"learning_prompt_version:{prompt['id']}",
        "source_type": "learning_prompt_version",
        "equipment_id": None,
        "title": f"Prompt version {prompt['assistant']} {prompt['version']}",
        "timestamp": prompt.get("created_at"),
        "content": (
            f"Prompt version {prompt['id']} for assistant {prompt.get('assistant')}: "
            f"version {prompt.get('version')}; status {prompt.get('status')}; notes {prompt.get('notes') or 'none'}. "
            f"Prompt: {prompt.get('prompt')}."
        ),
    }


def _learning_evaluation_plant_record(evaluation: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"learning_evaluation_run:{evaluation['id']}",
        "source_type": "learning_evaluation_run",
        "equipment_id": None,
        "title": f"Learning evaluation {evaluation['id']}",
        "timestamp": evaluation.get("created_at"),
        "content": (
            f"Learning evaluation run {evaluation['id']}: dataset {evaluation.get('dataset_id') or 'none'}; "
            f"model version {evaluation.get('model_version_id') or 'none'}; prompt version {evaluation.get('prompt_version_id') or 'none'}; "
            f"passed {evaluation.get('passed')}; metrics {evaluation.get('metrics')}; notes {evaluation.get('notes') or 'none'}."
        ),
    }


def _learning_promotion_plant_record(promotion: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"learning_model_promotion:{promotion['id']}",
        "source_type": "learning_model_promotion",
        "equipment_id": None,
        "title": f"Learning promotion {promotion['id']}",
        "timestamp": promotion.get("created_at"),
        "content": (
            f"Learning promotion {promotion['id']}: action {promotion.get('action')}; "
            f"model version {promotion.get('model_version_id')}; previous active {promotion.get('previous_active_model_id') or 'none'}; "
            f"evaluation {promotion.get('evaluation_run_id')}; dataset {promotion.get('dataset_id')}; "
            f"prompt version {promotion.get('prompt_version_id')}; reviewer {promotion.get('reviewer_email')}; "
            f"notes {promotion.get('notes') or 'none'}."
        ),
    }


def _learning_deployment_plant_record(deployment: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"learning_model_deployment:{deployment['id']}",
        "source_type": "learning_model_deployment",
        "equipment_id": None,
        "title": f"Learning deployment {deployment['id']}",
        "timestamp": deployment.get("updated_at") or deployment.get("created_at"),
        "content": (
            f"Learning deployment {deployment['id']} for model version {deployment.get('model_version_id')}: "
            f"job {deployment.get('job_id') or 'none'}; runtime provider {deployment.get('runtime_provider')}; "
            f"serving provider {deployment.get('serving_provider')}; served model {deployment.get('served_model_name')}; "
            f"base URL {deployment.get('base_url') or 'none'}; artifact URI {deployment.get('artifact_uri') or 'none'}; "
            f"status {deployment.get('status')}; health {deployment.get('health_status')}; "
            f"health checked {deployment.get('health_checked_at') or 'never'}; error {deployment.get('error') or 'none'}."
        ),
    }


def _learning_job_plant_record(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"learning_job:{job['id']}",
        "source_type": "learning_job",
        "equipment_id": None,
        "title": f"Learning job {job['job_type']} {job['id']}",
        "timestamp": job.get("updated_at") or job.get("created_at"),
        "content": (
            f"Learning job {job['id']}: type {job.get('job_type')}; subject {job.get('subject')}; "
            f"status {job.get('status')}; requested by {job.get('requested_by') or 'unknown'}; "
            f"correlation {job.get('correlation_id')}; retries {job.get('retry_count')}; "
            f"input refs {job.get('input_refs')}; output refs {job.get('output_refs')}; error {job.get('error') or 'none'}."
        ),
    }


def _rag_embedding_profile_plant_record(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"rag_embedding_profile:{profile['id']}",
        "source_type": "rag_embedding_profile",
        "equipment_id": None,
        "title": f"RAG embedding profile {profile['id']}",
        "timestamp": profile.get("updated_at") or profile.get("created_at"),
        "content": (
            f"RAG embedding profile {profile['id']}: provider {profile.get('provider')}; model {profile.get('model')}; "
            f"version {profile.get('version')}; dimensions {profile.get('dimensions')}; distance {profile.get('distance')}; "
            f"status {profile.get('status')}; notes {profile.get('notes') or 'none'}."
        ),
    }


def _learning_artifact_plant_record(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"learning_artifact:{artifact['id']}",
        "source_type": "learning_artifact",
        "equipment_id": None,
        "title": f"Learning artifact {artifact['artifact_type']}",
        "timestamp": artifact.get("created_at"),
        "content": (
            f"Learning artifact {artifact['id']} for job {artifact.get('job_id')}: type {artifact.get('artifact_type')}; "
            f"URI {artifact.get('uri')}; content hash {artifact.get('content_hash')}; metadata {artifact.get('metadata')}."
        ),
    }


def save_feedback(recommendation_id: str, feedback: dict[str, Any]) -> dict[str, Any]:
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
    latest = _fetch_one("SELECT * FROM feedback WHERE recommendation_id = ? ORDER BY created_at DESC, id DESC LIMIT 1", (recommendation_id,))
    if latest:
        return sync_plant_records_index([_feedback_plant_record(latest)])
    return {"store": "unknown", "indexed": 0, "state": "missing_feedback"}


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
    label = _fetch_one(
        "SELECT * FROM maintenance_labels WHERE source_type = ? AND source_id = ?",
        (payload["source_type"], payload["source_id"]),
    )
    if label:
        sync_plant_records_index([_maintenance_label_plant_record(_decode_maintenance_label(label))])


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
    sync_plant_records_index([_user_plant_record(user)])
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
    user = get_user_by_id(user_id)
    if user:
        sync_plant_records_index([_user_plant_record(user)])
    return user


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
    user = get_user_by_id(user_id)
    if user:
        sync_plant_records_index([_user_plant_record(user)])
    return user


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
    user = get_user_by_id(user_id)
    if user:
        sync_plant_records_index([_user_plant_record(user)])


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
    event = _fetch_one("SELECT * FROM auth_audit_events ORDER BY created_at DESC, id DESC LIMIT 1")
    if event:
        sync_plant_records_index([_auth_audit_event_plant_record(event)])


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
    message = get_streaming_message(message_id)
    if message:
        sync_plant_records_index([_streaming_message_plant_record(message)])


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
    sync_plant_records_index([_interaction_plant_record(interaction)])
    return interaction


def upsert_assistant_session(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_ready()
    session_id = payload.get("id") or f"ASST-{uuid.uuid4().hex[:12].upper()}"
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO assistant_sessions (
                id,
                assistant_id,
                user_id,
                user_role,
                screen,
                status,
                metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                assistant_id=excluded.assistant_id,
                user_id=excluded.user_id,
                user_role=excluded.user_role,
                screen=excluded.screen,
                status=excluded.status,
                metadata=excluded.metadata,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                session_id,
                payload["assistant_id"],
                payload.get("user_id"),
                payload.get("user_role"),
                payload.get("screen"),
                payload.get("status") or "active",
                _json_dump_any(payload.get("metadata", {})),
            ),
        )
    session = get_assistant_session(session_id)
    if not session:
        raise RuntimeError("Assistant session was not persisted")
    return session


def get_assistant_session(session_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one("SELECT * FROM assistant_sessions WHERE id = ?", (session_id,))
    return _decode_assistant_session(row) if row else None


def save_assistant_message(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_ready()
    message_id = payload.get("id") or f"AMSG-{uuid.uuid4().hex[:12].upper()}"
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO assistant_messages (
                id,
                session_id,
                assistant_id,
                role,
                content,
                provider,
                used_live_provider,
                tool_calls,
                tool_results,
                final_response,
                metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                payload["session_id"],
                payload["assistant_id"],
                payload["role"],
                payload.get("content") or "",
                payload.get("provider"),
                1 if payload.get("used_live_provider") else 0,
                _json_dump_any(payload.get("tool_calls", [])),
                _json_dump_any(payload.get("tool_results", [])),
                _json_dump_any(payload["final_response"]) if payload.get("final_response") is not None else None,
                _json_dump_any(payload.get("metadata", {})),
            ),
        )
        connection.execute(
            """
            UPDATE assistant_sessions
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (payload["session_id"],),
        )
    message = get_assistant_message(message_id)
    if not message:
        raise RuntimeError("Assistant message was not persisted")
    return message


def get_assistant_message(message_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one("SELECT * FROM assistant_messages WHERE id = ?", (message_id,))
    return _decode_assistant_message(row) if row else None


def list_assistant_messages(session_id: str, limit: int = 20) -> list[dict[str, Any]]:
    rows = _fetch_all(
        """
        SELECT *
        FROM assistant_messages
        WHERE session_id = ?
        ORDER BY created_at DESC, rowid DESC
        LIMIT ?
        """,
        (session_id, limit),
    )
    return [_decode_assistant_message(row) for row in reversed(rows)]


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
    sync_plant_records_index([_learning_example_plant_record(example)])
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
    offset: int = 0,
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
    params.extend([limit, offset])
    rows = _fetch_all(
        f"""
        SELECT * FROM learning_examples
        {where}
        ORDER BY approved DESC, created_at DESC
        LIMIT ? OFFSET ?
        """,
        tuple(params),
    )
    return [_decode_learning_example(row) for row in rows]


def count_learning_examples(
    approved_only: Optional[bool] = None,
    equipment_id: Optional[str] = None,
    min_judge_score: Optional[float] = None,
) -> int:
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
    row = _fetch_one(f"SELECT COUNT(*) AS count FROM learning_examples {where}", tuple(params))
    return int(row["count"]) if row else 0


def set_learning_example_approval(example_id: str, approved: bool) -> Optional[dict[str, Any]]:
    ensure_ready()
    with connect() as connection:
        connection.execute(
            "UPDATE learning_examples SET approved = ? WHERE id = ?",
            (1 if approved else 0, example_id),
        )
    example = get_learning_example(example_id)
    if example:
        sync_plant_records_index([_learning_example_plant_record(example)])
    return example


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
    example = get_learning_example(example_id)
    if example:
        sync_plant_records_index([_learning_example_plant_record(example)])
    return example


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
    sync_plant_records_index([_learning_snapshot_plant_record(snapshot)])
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
    sync_plant_records_index([_rag_embedding_profile_plant_record(profile)])
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
    profile = get_rag_embedding_profile(profile_id)
    if profile:
        sync_plant_records_index([_rag_embedding_profile_plant_record(profile)])
    return profile


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
    model_dict = dict(model)
    sync_plant_records_index([_learning_model_version_plant_record(model_dict)])
    return model_dict


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
    model = get_learning_model_version(model_id)
    if model:
        sync_plant_records_index([_learning_model_version_plant_record(model)])
    return model


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
    sync_plant_records_index([_learning_evaluation_plant_record(run)])
    return run


def get_learning_evaluation_run(run_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one("SELECT * FROM learning_evaluation_runs WHERE id = ?", (run_id,))
    return _decode_learning_evaluation(row) if row else None


def list_learning_evaluation_runs(limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
    rows = _fetch_all(
        """
        SELECT * FROM learning_evaluation_runs
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    )
    return [_decode_learning_evaluation(row) for row in rows]


def count_learning_evaluation_runs() -> int:
    row = _fetch_one("SELECT COUNT(*) AS count FROM learning_evaluation_runs")
    return int(row["count"]) if row else 0


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
    sync_plant_records_index([_learning_promotion_plant_record(promotion)])
    return promotion


def get_learning_model_promotion(promotion_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one("SELECT * FROM learning_model_promotions WHERE id = ?", (promotion_id,))
    return dict(row) if row else None


def list_learning_model_promotions(limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT * FROM learning_model_promotions
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    )


def count_learning_model_promotions() -> int:
    row = _fetch_one("SELECT COUNT(*) AS count FROM learning_model_promotions")
    return int(row["count"]) if row else 0


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
    sync_plant_records_index([_learning_deployment_plant_record(deployment)])
    return deployment


def get_learning_model_deployment(deployment_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one("SELECT * FROM learning_model_deployments WHERE id = ?", (deployment_id,))
    return _decode_learning_model_deployment(row) if row else None


def list_learning_model_deployments(
    *,
    model_version_id: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    if model_version_id:
        rows = _fetch_all(
            """
            SELECT * FROM learning_model_deployments
            WHERE model_version_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (model_version_id, limit, offset),
        )
    else:
        rows = _fetch_all(
            """
            SELECT * FROM learning_model_deployments
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
    return [_decode_learning_model_deployment(row) for row in rows]


def count_learning_model_deployments(model_version_id: Optional[str] = None) -> int:
    if model_version_id:
        row = _fetch_one("SELECT COUNT(*) AS count FROM learning_model_deployments WHERE model_version_id = ?", (model_version_id,))
    else:
        row = _fetch_one("SELECT COUNT(*) AS count FROM learning_model_deployments")
    return int(row["count"]) if row else 0


def get_verified_learning_model_deployment(model_version_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one(
        """
        SELECT * FROM learning_model_deployments
        WHERE model_version_id = ?
          AND status = 'verified'
          AND health_status IN ('healthy', 'ok', 'ready')
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
    sync_plant_records_index([_learning_job_plant_record(job)])
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
    job = get_learning_job(job_id)
    if job:
        sync_plant_records_index([_learning_job_plant_record(job)])
    return job


def get_learning_job(job_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one("SELECT * FROM learning_jobs WHERE id = ?", (job_id,))
    return _decode_learning_job(row) if row else None


def list_learning_jobs(limit: int = 20, status: Optional[str] = None, offset: int = 0) -> list[dict[str, Any]]:
    if status:
        rows = _fetch_all(
            """
            SELECT * FROM learning_jobs
            WHERE status = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (status, limit, offset),
        )
    else:
        rows = _fetch_all(
            """
            SELECT * FROM learning_jobs
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
    return [_decode_learning_job(row) for row in rows]


def count_learning_jobs(status: Optional[str] = None) -> int:
    if status:
        row = _fetch_one("SELECT COUNT(*) AS count FROM learning_jobs WHERE status = ?", (status,))
    else:
        row = _fetch_one("SELECT COUNT(*) AS count FROM learning_jobs")
    return int(row["count"]) if row else 0


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
    sync_plant_records_index([_learning_artifact_plant_record(artifact)])
    return artifact


def get_learning_artifact(artifact_id: str) -> Optional[dict[str, Any]]:
    row = _fetch_one("SELECT * FROM learning_artifacts WHERE id = ?", (artifact_id,))
    return _decode_learning_artifact(row) if row else None


def list_learning_artifacts(job_id: Optional[str] = None, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
    if job_id:
        rows = _fetch_all(
            """
            SELECT * FROM learning_artifacts
            WHERE job_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (job_id, limit, offset),
        )
    else:
        rows = _fetch_all(
            """
            SELECT * FROM learning_artifacts
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
    return [_decode_learning_artifact(row) for row in rows]


def count_learning_artifacts(job_id: Optional[str] = None) -> int:
    if job_id:
        row = _fetch_one("SELECT COUNT(*) AS count FROM learning_artifacts WHERE job_id = ?", (job_id,))
    else:
        row = _fetch_one("SELECT COUNT(*) AS count FROM learning_artifacts")
    return int(row["count"]) if row else 0


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


def _decode_notification_event(row: dict[str, Any]) -> dict[str, Any]:
    event = dict(row)
    event["recipient_roles"] = _json_load_list(event.get("recipient_roles"))
    event["recipient_user_ids"] = _json_load_list(event.get("recipient_user_ids"))
    event["metadata"] = _json_load_dict(event.get("metadata"))
    event["llm_used_live_provider"] = bool(event.get("llm_used_live_provider"))
    event["seen_at"] = event.get("seen_at")
    event["dismissed_at"] = event.get("dismissed_at")
    return event


def _superseded_assignment_notification_candidates() -> list[dict[str, Any]]:
    rows = _fetch_all(
        """
        SELECT *
        FROM notification_events
        WHERE event_type = 'work_order_assigned'
            AND work_order_id IS NOT NULL
            AND recipient_user_ids <> '[]'
        ORDER BY created_at DESC, id DESC
        """
    )
    grouped: dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]] = {}
    for row in rows:
        event = _decode_notification_event(row)
        key = (str(event.get("work_order_id")), tuple(event.get("recipient_user_ids") or []))
        grouped.setdefault(key, []).append(event)

    candidates: list[dict[str, Any]] = []
    for group in grouped.values():
        if len(group) <= 1:
            continue
        for event in group[1:]:
            candidates.append(_notification_cleanup_candidate(event, "superseded_assignment"))
    return candidates


def _dismissed_direct_notification_candidates(cutoff: datetime) -> list[dict[str, Any]]:
    rows = _fetch_all(
        """
        SELECT *
        FROM notification_events
        WHERE recipient_roles = '[]'
            AND recipient_user_ids <> '[]'
        """
    )
    candidates: list[dict[str, Any]] = []
    for row in rows:
        event = _decode_notification_event(row)
        recipient_user_ids = event.get("recipient_user_ids") or []
        if not recipient_user_ids:
            continue
        views = _fetch_all(
            """
            SELECT user_id, dismissed_at
            FROM user_notification_views
            WHERE notification_id = ?
            """,
            (event["id"],),
        )
        dismissed_by_user = {
            view["user_id"]: _parse_sqlite_timestamp(view["dismissed_at"])
            for view in views
            if view.get("dismissed_at")
        }
        if all(
            dismissed_by_user.get(user_id) and dismissed_by_user[user_id] <= cutoff
            for user_id in recipient_user_ids
        ):
            candidates.append(_notification_cleanup_candidate(event, "dismissed_direct_notification"))
    return candidates


def _notification_cleanup_candidate(event: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "id": event["id"],
        "event_type": event["event_type"],
        "reason": reason,
        "title": event["title"],
        "work_order_id": event.get("work_order_id"),
        "alert_id": event.get("alert_id"),
        "recipient_roles": event.get("recipient_roles") or [],
        "recipient_user_ids": event.get("recipient_user_ids") or [],
        "created_at": event["created_at"],
    }


def _parse_sqlite_timestamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _notification_targets_user(notification: dict[str, Any], user_id: str, role: str) -> bool:
    recipient_user_ids = set(notification.get("recipient_user_ids") or [])
    recipient_roles = set(notification.get("recipient_roles") or [])
    return user_id in recipient_user_ids or role in recipient_roles


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


def _decode_assistant_session(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    decoded["metadata"] = _json_load_dict(decoded.get("metadata"))
    return decoded


def _decode_assistant_message(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    decoded["used_live_provider"] = bool(decoded.get("used_live_provider"))
    decoded["tool_calls"] = _json_load_any(decoded.get("tool_calls")) or []
    decoded["tool_results"] = _json_load_any(decoded.get("tool_results")) or []
    decoded["final_response"] = _json_load_any(decoded.get("final_response"))
    decoded["metadata"] = _json_load_dict(decoded.get("metadata"))
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
    decoded["spare_reservations"] = [
        _decode_work_order_spare(item)
        for item in _fetch_all(
            "SELECT * FROM work_order_spares WHERE work_order_id = ? ORDER BY id ASC",
            (decoded["id"],),
        )
    ]
    if include_logs:
        decoded["logs"] = _fetch_all(
            "SELECT * FROM work_order_logs WHERE work_order_id = ? ORDER BY created_at ASC, id ASC",
            (decoded["id"],),
        )
    else:
        decoded["logs"] = []
    return decoded


def _decode_work_order_spare(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    decoded["reorder_requested"] = bool(decoded.get("reorder_requested"))
    return decoded


def _decode_rca_case(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    decoded["symptoms"] = _json_load_any(decoded.get("symptoms")) or []
    decoded["hypotheses"] = _json_load_any(decoded.get("hypotheses")) or []
    decoded["why_chain"] = _json_load_any(decoded.get("why_chain")) or []
    decoded["fishbone"] = _json_load_dict(decoded.get("fishbone"))
    decoded["evidence_timeline"] = _json_load_any(decoded.get("evidence_timeline")) or []
    decoded["corrective_actions"] = _json_load_any(decoded.get("corrective_actions")) or []
    decoded["closure_review"] = _json_load_any(decoded.get("closure_review"))
    decoded["confidence"] = float(decoded.get("confidence") or 0)
    decoded["missing_checks"] = _json_load_any(decoded.get("missing_checks")) or []
    decoded["used_live_provider"] = bool(decoded.get("used_live_provider"))
    return decoded


def _decode_pm_template(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    decoded["cadence_days"] = int(decoded.get("cadence_days") or 30)
    decoded["task_list"] = _json_load_any(decoded.get("task_list")) or []
    decoded["thresholds"] = _json_load_any(decoded.get("thresholds")) or []
    return decoded


def _decode_pm_plan(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    decoded["cadence_days"] = int(decoded.get("cadence_days") or 30)
    decoded["trigger"] = _json_load_dict(decoded.get("trigger"))
    decoded["thresholds"] = _json_load_any(decoded.get("thresholds")) or []
    decoded["tasks"] = _json_load_any(decoded.get("tasks")) or []
    decoded["smith_steps"] = _json_load_any(decoded.get("smith_steps")) or []
    decoded["spares_strategy"] = _json_load_any(decoded.get("spares_strategy")) or []
    decoded["evidence"] = _json_load_any(decoded.get("evidence")) or []
    decoded["adjustment_notes"] = _json_load_any(decoded.get("adjustment_notes")) or []
    decoded["used_live_provider"] = bool(decoded.get("used_live_provider"))
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


def _next_rca_case_id() -> str:
    rows = _fetch_all("SELECT id FROM rca_cases WHERE id LIKE 'RCA-%'")
    numeric_ids: list[int] = []
    for row in rows:
        try:
            numeric_ids.append(int(str(row["id"]).split("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    next_number = max(numeric_ids, default=9000) + 1
    return f"RCA-{next_number}"


def _next_pm_plan_id() -> str:
    rows = _fetch_all("SELECT id FROM pm_plans WHERE id LIKE 'PM-%'")
    numeric_ids: list[int] = []
    for row in rows:
        try:
            numeric_ids.append(int(str(row["id"]).split("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    next_number = max(numeric_ids, default=7000) + 1
    return f"PM-{next_number}"


def _fetch_all(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    ensure_ready()
    with connect() as connection:
        return [dict(row) for row in connection.execute(sql, params).fetchall()]


def _fetch_one(sql: str, params: tuple[Any, ...] = ()) -> Optional[dict[str, Any]]:
    ensure_ready()
    with connect() as connection:
        row = connection.execute(sql, params).fetchone()
        return dict(row) if row else None
