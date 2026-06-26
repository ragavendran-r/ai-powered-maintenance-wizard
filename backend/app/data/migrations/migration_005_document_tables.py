"""Document tables migration - Documents, chunks, and intelligence."""

SCHEMA_VERSION = "005"
DESCRIPTION = "Add document management and intelligence tables"


def up(connection) -> None:
    """Apply the document tables schema."""
    # Documents table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            content_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source TEXT NOT NULL,
            metadata TEXT
        )
        """
    )
    
    # Document chunks table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS document_chunks (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            embedding BLOB,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents(id)
        )
        """
    )
    
    # Document intelligence table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS document_intelligence (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            summary TEXT,
            key_points TEXT,
            equipment_mentions TEXT,
            maintenance_relevance TEXT,
            confidence REAL,
            processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents(id)
        )
        """
    )
    
    # SOP/manual evidence table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS sop_manual_evidence (
            id TEXT PRIMARY KEY,
            equipment_id TEXT NOT NULL,
            document_id TEXT,
            title TEXT NOT NULL,
            section TEXT,
            content TEXT NOT NULL,
            relevance_score REAL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (equipment_id) REFERENCES equipment(id),
            FOREIGN KEY (document_id) REFERENCES documents(id)
        )
        """
    )


def down(connection) -> None:
    """Rollback the document tables."""
    tables = [
        "sop_manual_evidence",
        "document_intelligence",
        "document_chunks",
        "documents"
    ]
    
    for table in tables:
        connection.execute(f"DROP TABLE IF EXISTS {table}")
