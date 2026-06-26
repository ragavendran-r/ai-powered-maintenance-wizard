"""RCA and PM tables migration - Root cause analysis and preventive maintenance."""

SCHEMA_VERSION = "004"
DESCRIPTION = "Add RCA and preventive maintenance planning tables"


def up(connection) -> None:
    """Apply the RCA and PM tables schema."""
    # RCA cases table
    connection.execute(
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
        """
    )
    
    # PM templates table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS pm_templates (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            equipment_type TEXT NOT NULL,
            interval_days INTEGER NOT NULL,
            tasks TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    
    # PM plans table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS pm_plans (
            id TEXT PRIMARY KEY,
            template_id TEXT,
            equipment_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            scheduled_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            priority INTEGER NOT NULL DEFAULT 2,
            tasks TEXT NOT NULL,
            estimated_duration_hours REAL,
            required_spares TEXT,
            smith_steps TEXT,
            work_order_id TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (template_id) REFERENCES pm_templates(id),
            FOREIGN KEY (equipment_id) REFERENCES equipment(id),
            FOREIGN KEY (work_order_id) REFERENCES work_orders(id)
        )
        """
    )
    
    # Planner schedules table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS planner_schedules (
            id TEXT PRIMARY KEY,
            equipment_id TEXT NOT NULL,
            work_order_id TEXT,
            planned_start TEXT NOT NULL,
            planned_end TEXT NOT NULL,
            outage_window TEXT,
            assigned_team TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (equipment_id) REFERENCES equipment(id),
            FOREIGN KEY (work_order_id) REFERENCES work_orders(id)
        )
        """
    )


def down(connection) -> None:
    """Rollback the RCA and PM tables."""
    tables = [
        "planner_schedules",
        "pm_plans",
        "pm_templates",
        "rca_cases"
    ]
    
    for table in tables:
        connection.execute(f"DROP TABLE IF EXISTS {table}")
