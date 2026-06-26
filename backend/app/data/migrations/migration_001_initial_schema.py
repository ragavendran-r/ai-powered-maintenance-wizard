"""Initial schema migration - Complete database schema."""

SCHEMA_VERSION = "001"
DESCRIPTION = "Complete initial schema with all tables"


def up(connection) -> None:
    """Apply the complete initial schema."""
    # Schema metadata table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    
    # Equipment table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS equipment (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            area TEXT NOT NULL,
            process TEXT NOT NULL,
            criticality INTEGER NOT NULL,
            status TEXT NOT NULL
        )
        """
    )
    
    # Asset profiles table
    connection.execute(
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
        """
    )
    
    # Asset metric snapshots table
    connection.execute(
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
        """
    )
    
    # Asset recommendations table
    connection.execute(
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
        """
    )
    
    # Asset subsystems table
    connection.execute(
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
        """
    )
    
    # Asset reliability metrics table
    connection.execute(
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
        """
    )
    
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
        """
    )
    
    # PM plans table
    connection.execute(
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
    
    # Documents table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            equipment_id TEXT,
            title TEXT NOT NULL,
            content TEXT NOT NULL
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
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(provider, model, version, dimensions, distance)
        )
        """
    )
    
    # Document intelligence table
    connection.execute(
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
    
    # Feedback table
    connection.execute(
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
        """
    )
    
    # Maintenance labels table
    connection.execute(
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
        """
    )
    
    # Streaming messages table
    connection.execute(
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
        """
    )
    
    # User alert views table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS user_alert_views (
            user_id TEXT NOT NULL,
            alert_id TEXT NOT NULL,
            first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            dismissed_at TEXT,
            PRIMARY KEY (user_id, alert_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (alert_id) REFERENCES alerts(id)
        )
        """
    )
    
    # Notification events table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_events (
            id TEXT PRIMARY KEY,
            event_key TEXT NOT NULL UNIQUE,
            event_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            recommended_action TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            equipment_id TEXT,
            work_order_id TEXT,
            alert_id TEXT,
            recommendation_id TEXT,
            actor_user_id TEXT,
            actor_display_name TEXT,
            recipient_roles TEXT NOT NULL DEFAULT '[]',
            recipient_user_ids TEXT NOT NULL DEFAULT '[]',
            metadata TEXT NOT NULL DEFAULT '{}',
            llm_provider TEXT NOT NULL DEFAULT 'mock',
            llm_used_live_provider INTEGER NOT NULL DEFAULT 0,
            llm_status TEXT NOT NULL DEFAULT 'not_requested',
            llm_error TEXT,
            llm_requested_at TEXT,
            llm_completed_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    
    # User notification views table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS user_notification_views (
            user_id TEXT NOT NULL,
            notification_id TEXT NOT NULL,
            first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            dismissed_at TEXT,
            PRIMARY KEY (user_id, notification_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (notification_id) REFERENCES notification_events(id)
        )
        """
    )
    
    # Users table
    connection.execute(
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
        """
    )
    
    # Auth audit events table
    connection.execute(
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
        """
    )
    
    # Learning interactions table
    connection.execute(
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
        """
    )
    
    # Assistant sessions table
    connection.execute(
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
        """
    )
    
    # Assistant messages table
    connection.execute(
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
        """
    )
    
    # Learning examples table
    connection.execute(
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
            approved_only INTEGER NOT NULL DEFAULT 1,
            jsonl_content TEXT NOT NULL,
            created_by TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    
    # Learning model versions table
    connection.execute(
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
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(assistant, version)
        )
        """
    )
    
    # Learning evaluation runs table
    connection.execute(
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
        """
    )
    
    # Learning jobs table
    connection.execute(
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
        """
    )
    
    # Learning artifacts table
    connection.execute(
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
        """
    )
    
    # Learning model promotions table
    connection.execute(
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
        """
    )
    
    # Learning model deployments table
    connection.execute(
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
    """Rollback the initial schema."""
    tables = [
        "asset_reliability_metrics",
        "asset_subsystems", 
        "asset_recommendations",
        "asset_metric_snapshots",
        "asset_profiles",
        "equipment",
        "schema_metadata"
    ]
    
    for table in tables:
        connection.execute(f"DROP TABLE IF EXISTS {table}")
