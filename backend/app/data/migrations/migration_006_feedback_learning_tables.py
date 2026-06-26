"""Feedback and learning tables migration - Maintenance labels and learning examples."""

SCHEMA_VERSION = "006"
DESCRIPTION = "Add feedback capture and learning system tables"


def up(connection) -> None:
    """Apply the feedback and learning tables schema."""
    # Maintenance labels table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS maintenance_labels (
            id TEXT PRIMARY KEY,
            equipment_id TEXT NOT NULL,
            failure_mode TEXT NOT NULL,
            component TEXT NOT NULL,
            action_class TEXT NOT NULL,
            outcome TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (equipment_id) REFERENCES equipment(id)
        )
        """
    )
    
    # Feedback table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback (
            id TEXT PRIMARY KEY,
            equipment_id TEXT NOT NULL,
            user_id TEXT,
            root_cause TEXT,
            action_taken TEXT,
            outcome TEXT,
            usefulness INTEGER,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (equipment_id) REFERENCES equipment(id)
        )
        """
    )
    
    # Learning examples table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_examples (
            id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            source_id TEXT,
            equipment_id TEXT,
            input_data TEXT NOT NULL,
            output_data TEXT NOT NULL,
            metadata TEXT,
            quality_score REAL,
            judge_rationale TEXT,
            approval_status TEXT NOT NULL DEFAULT 'pending',
            approved_by TEXT,
            approved_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (equipment_id) REFERENCES equipment(id)
        )
        """
    )
    
    # Learning dataset snapshots table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_dataset_snapshots (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            example_count INTEGER NOT NULL,
            criteria TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT
        )
        """
    )


def down(connection) -> None:
    """Rollback the feedback and learning tables."""
    tables = [
        "learning_dataset_snapshots",
        "learning_examples",
        "feedback",
        "maintenance_labels"
    ]
    
    for table in tables:
        connection.execute(f"DROP TABLE IF EXISTS {table}")
