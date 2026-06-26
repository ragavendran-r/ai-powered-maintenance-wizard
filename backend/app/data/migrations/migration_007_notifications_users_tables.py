"""Notifications and users tables migration - User management and notifications."""

SCHEMA_VERSION = "007"
DESCRIPTION = "Add user management and notification system tables"


def up(connection) -> None:
    """Apply the notifications and users tables schema."""
    # Users table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_login_at TEXT
        )
        """
    )
    
    # Notification events table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_events (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            data TEXT,
            seen INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    
    # Notification cleanup records table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_cleanup_records (
            id TEXT PRIMARY KEY,
            cleaned_by TEXT NOT NULL,
            events_removed INTEGER NOT NULL,
            cleaned_before TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def down(connection) -> None:
    """Rollback the notifications and users tables."""
    tables = [
        "notification_cleanup_records",
        "notification_events",
        "users"
    ]
    
    for table in tables:
        connection.execute(f"DROP TABLE IF EXISTS {table}")
