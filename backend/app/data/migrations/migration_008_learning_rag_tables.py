"""Learning and RAG tables migration - Model management and vector search."""

SCHEMA_VERSION = "008"
DESCRIPTION = "Add learning model management and RAG vector search tables"


def up(connection) -> None:
    """Apply the learning and RAG tables schema."""
    # Learning jobs table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_jobs (
            id TEXT PRIMARY KEY,
            job_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            request_data TEXT NOT NULL,
            result_data TEXT,
            error_message TEXT,
            started_at TEXT,
            completed_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    
    # Learning model versions table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_model_versions (
            id TEXT PRIMARY KEY,
            model_type TEXT NOT NULL,
            version TEXT NOT NULL,
            base_model TEXT NOT NULL,
            adapter_path TEXT,
            metadata TEXT,
            status TEXT NOT NULL DEFAULT 'candidate',
            performance_metrics TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT
        )
        """
    )
    
    # Learning model deployments table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_model_deployments (
            id TEXT PRIMARY KEY,
            model_version_id TEXT NOT NULL,
            deployment_type TEXT NOT NULL,
            endpoint_url TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            deployed_at TEXT,
            health_status TEXT,
            last_health_check TEXT,
            metadata TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (model_version_id) REFERENCES learning_model_versions(id)
        )
        """
    )
    
    # Learning model promotions table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_model_promotions (
            id TEXT PRIMARY KEY,
            from_version_id TEXT NOT NULL,
            to_version_id TEXT NOT NULL,
            promoted_by TEXT NOT NULL,
            reason TEXT,
            promoted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (from_version_id) REFERENCES learning_model_versions(id),
            FOREIGN KEY (to_version_id) REFERENCES learning_model_versions(id)
        )
        """
    )
    
    # Learning artifacts table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_artifacts (
            id TEXT PRIMARY KEY,
            artifact_type TEXT NOT NULL,
            storage_type TEXT NOT NULL,
            path TEXT NOT NULL,
            metadata TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT
        )
        """
    )
    
    # RAG embedding profiles table
    connection.execute(
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
            metadata TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    
    # Learning prompt versions table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_prompt_versions (
            id TEXT PRIMARY KEY,
            assistant TEXT NOT NULL,
            version TEXT NOT NULL,
            prompt TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'candidate',
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def down(connection) -> None:
    """Rollback the learning and RAG tables."""
    tables = [
        "learning_prompt_versions",
        "rag_embedding_profiles",
        "learning_artifacts",
        "learning_model_promotions",
        "learning_model_deployments",
        "learning_model_versions",
        "learning_jobs"
    ]
    
    for table in tables:
        connection.execute(f"DROP TABLE IF EXISTS {table}")
