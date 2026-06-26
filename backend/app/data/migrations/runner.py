"""Migration runner for database schema management."""

import importlib
import sqlite3
from pathlib import Path
from typing import Any


class MigrationRunner:
    """Handles database schema migrations."""
    
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.migrations_dir = Path(__file__).parent
        
    def get_current_version(self) -> str:
        """Get the current schema version from the database."""
        cursor = self.connection.execute(
            "SELECT value FROM schema_metadata WHERE key = 'schema_version'"
        )
        row = cursor.fetchone()
        if row:
            return row[0]
        return "000"
    
    def set_schema_version(self, version: str) -> None:
        """Set the current schema version in the database."""
        self.connection.execute(
            """
            INSERT INTO schema_metadata (key, value)
            VALUES ('schema_version', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (version,)
        )
    
    def get_available_migrations(self) -> list[tuple[str, Any]]:
        """Get all available migration files sorted by version."""
        migrations = []
        
        for migration_file in sorted(self.migrations_dir.glob("migration_*.py")):
            if migration_file.name == "__init__.py" or migration_file.name == "runner.py":
                continue
                
            module_name = f"app.data.migrations.{migration_file.stem}"
            module = importlib.import_module(module_name)
            
            if hasattr(module, 'SCHEMA_VERSION') and hasattr(module, 'DESCRIPTION'):
                migrations.append((module.SCHEMA_VERSION, module))
        
        return sorted(migrations, key=lambda x: x[0])
    
    def migrate(self, target_version: str | None = None) -> None:
        """Run migrations to bring database to target version."""
        current_version = self.get_current_version()
        available_migrations = self.get_available_migrations()
        
        if target_version is None:
            # Migrate to latest
            target_version = available_migrations[-1][0] if available_migrations else current_version
        
        # Filter migrations that need to be applied
        pending_migrations = [
            (version, module) for version, module in available_migrations
            if version > current_version and version <= target_version
        ]
        
        for version, module in pending_migrations:
            print(f"Applying migration {version}: {module.DESCRIPTION}")
            try:
                module.up(self.connection)
                self.set_schema_version(version)
                print(f"Migration {version} completed successfully")
            except Exception as e:
                print(f"Migration {version} failed: {e}")
                raise
    
    def rollback(self, target_version: str) -> None:
        """Rollback migrations to target version."""
        current_version = self.get_current_version()
        available_migrations = self.get_available_migrations()
        
        # Filter migrations that need to be rolled back
        migrations_to_rollback = [
            (version, module) for version, module in available_migrations
            if version > target_version and version <= current_version
        ]
        
        # Rollback in reverse order
        for version, module in reversed(migrations_to_rollback):
            print(f"Rolling back migration {version}: {module.DESCRIPTION}")
            try:
                module.down(self.connection)
                # Set version to the previous migration
                previous_version = target_version
                self.set_schema_version(previous_version)
                print(f"Rollback {version} completed successfully")
            except Exception as e:
                print(f"Rollback {version} failed: {e}")
                raise
    
    def initialize_schema_metadata(self) -> None:
        """Initialize the schema metadata table if it doesn't exist."""
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        
        # Set initial version if not set
        current = self.get_current_version()
        if current == "000":
            self.set_schema_version("000")