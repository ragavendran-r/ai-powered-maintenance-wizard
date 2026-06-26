"""Monitoring tables migration - Alerts, spares, and sensor readings."""

SCHEMA_VERSION = "002"
DESCRIPTION = "Add monitoring tables for alerts, spares, and sensor readings"


def up(connection) -> None:
    """Apply the monitoring tables schema."""
    # Alerts table
    connection.execute(
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
        """
    )
    
    # Spares table
    connection.execute(
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
        """
    )
    
    # Sensor readings table
    connection.execute(
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
        """
    )
    
    # Maintenance events table
    connection.execute(
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
        """
    )


def down(connection) -> None:
    """Rollback the monitoring tables."""
    tables = [
        "maintenance_events",
        "sensor_readings",
        "spares",
        "alerts"
    ]
    
    for table in tables:
        connection.execute(f"DROP TABLE IF EXISTS {table}")
