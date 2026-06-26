"""Work order tables migration - Work orders, spares, and logs."""

SCHEMA_VERSION = "003"
DESCRIPTION = "Add work order management tables"


def up(connection) -> None:
    """Apply the work order tables schema."""
    # Work orders table
    connection.execute(
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
        """
    )
    
    # Work order spares table
    connection.execute(
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
        """
    )
    
    # Work order logs table
    connection.execute(
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
        """
    )


def down(connection) -> None:
    """Rollback the work order tables."""
    tables = [
        "work_order_logs",
        "work_order_spares",
        "work_orders"
    ]
    
    for table in tables:
        connection.execute(f"DROP TABLE IF EXISTS {table}")
