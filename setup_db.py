"""SIRM — Secure Intelligent Release Management"""
import os
import json
import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL", "")

def init_tables():
    """Initialize all SIRM database tables."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable required")

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sirm_config (key VARCHAR(64) PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS sirm_tasks (
        id VARCHAR(64) PRIMARY KEY,
        title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
        status VARCHAR(32) NOT NULL DEFAULT 'backlog',
        stage VARCHAR(32) NOT NULL DEFAULT 'plan',
        role VARCHAR(64) NOT NULL DEFAULT 'line_worker',
        assigned_to VARCHAR(128) NOT NULL DEFAULT '',
        priority INTEGER NOT NULL DEFAULT 3,
        acceptance_criteria JSONB NOT NULL DEFAULT '[]',
        dependencies JSONB NOT NULL DEFAULT '[]',
        security_considerations TEXT NOT NULL DEFAULT '',
        evidence JSONB NOT NULL DEFAULT '[]',
        tags JSONB NOT NULL DEFAULT '[]',
        activity_log JSONB NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS sirm_memories (
        id VARCHAR(64) PRIMARY KEY,
        category VARCHAR(64) NOT NULL DEFAULT 'operational',
        content TEXT NOT NULL, source VARCHAR(128) NOT NULL DEFAULT '',
        tags JSONB NOT NULL DEFAULT '[]', created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS sirm_gates (
        id VARCHAR(64) PRIMARY KEY,
        name VARCHAR(128) NOT NULL, stage VARCHAR(32) NOT NULL DEFAULT 'plan',
        gate_type VARCHAR(32) NOT NULL DEFAULT 'manual',
        description TEXT NOT NULL DEFAULT '',
        status VARCHAR(32) NOT NULL DEFAULT 'not_run',
        last_run TEXT, evidence TEXT NOT NULL DEFAULT '',
        command TEXT NOT NULL DEFAULT '',
        last_output TEXT NOT NULL DEFAULT '',
        last_exit_code INTEGER, run_count INTEGER NOT NULL DEFAULT 0,
        execution_history JSONB NOT NULL DEFAULT '[]'
    );
    CREATE TABLE IF NOT EXISTS sirm_sessions (
        id VARCHAR(64) PRIMARY KEY,
        started_at TEXT NOT NULL, ended_at TEXT,
        worker VARCHAR(128) NOT NULL DEFAULT '',
        role VARCHAR(64) NOT NULL DEFAULT 'line_worker',
        tasks_worked JSONB NOT NULL DEFAULT '[]',
        notes TEXT NOT NULL DEFAULT '',
        baton_pass JSONB NOT NULL DEFAULT '{}', active BOOLEAN NOT NULL DEFAULT TRUE
    );
    CREATE TABLE IF NOT EXISTS sirm_forge_items (
        id VARCHAR(64) PRIMARY KEY,
        raw_input TEXT NOT NULL, source VARCHAR(128) NOT NULL DEFAULT '',
        status VARCHAR(32) NOT NULL DEFAULT 'raw',
        extracted_title TEXT NOT NULL DEFAULT '',
        extracted_description TEXT NOT NULL DEFAULT '',
        extracted_type VARCHAR(64) NOT NULL DEFAULT '',
        suggested_priority INTEGER DEFAULT 3,
        suggested_role VARCHAR(64) NOT NULL DEFAULT 'line_worker',
        suggested_stage VARCHAR(32) NOT NULL DEFAULT 'plan',
        suggested_tags JSONB NOT NULL DEFAULT '[]',
        suggested_product_line VARCHAR(128) NOT NULL DEFAULT '',
        suggested_project VARCHAR(128) NOT NULL DEFAULT '',
        confidence_score REAL DEFAULT 0,
        gate_results JSONB NOT NULL DEFAULT '{}',
        gate_score REAL DEFAULT 0,
        related_existing JSONB NOT NULL DEFAULT '[]',
        extraction_notes JSONB NOT NULL DEFAULT '[]',
        work_order_id VARCHAR(64),
        rejection_reason TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS agent_context (
        context_key VARCHAR(128) PRIMARY KEY,
        context_value TEXT NOT NULL,
        category VARCHAR(64) NOT NULL DEFAULT 'operational',
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS agent_directives (
        id SERIAL PRIMARY KEY,
        directive TEXT NOT NULL,
        priority INTEGER NOT NULL DEFAULT 2,
        category VARCHAR(64) NOT NULL DEFAULT 'general',
        source VARCHAR(128) NOT NULL DEFAULT 'system',
        active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS agent_sessions (
        session_id VARCHAR(128) PRIMARY KEY,
        repl_name VARCHAR(128) NOT NULL DEFAULT '',
        started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        ended_at TIMESTAMPTZ,
        summary TEXT NOT NULL DEFAULT '',
        tasks_completed JSONB NOT NULL DEFAULT '[]',
        tasks_started JSONB NOT NULL DEFAULT '[]',
        decisions_made JSONB NOT NULL DEFAULT '[]',
        escalations JSONB NOT NULL DEFAULT '[]',
        next_actions JSONB NOT NULL DEFAULT '[]'
    );
    CREATE TABLE IF NOT EXISTS agent_chat_log (
        id SERIAL PRIMARY KEY,
        session_id VARCHAR(128) NOT NULL,
        worker_id VARCHAR(128) NOT NULL DEFAULT '',
        role VARCHAR(32) NOT NULL DEFAULT 'assistant',
        content TEXT NOT NULL,
        source VARCHAR(64) NOT NULL DEFAULT 'replit',
        repl_name VARCHAR(128) NOT NULL DEFAULT '',
        metadata JSONB NOT NULL DEFAULT '{}',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS agent_workers (
        id VARCHAR(128) PRIMARY KEY,
        worker_type VARCHAR(64) NOT NULL DEFAULT 'replit_agent',
        repl_name VARCHAR(128) NOT NULL DEFAULT '',
        environment VARCHAR(64) NOT NULL DEFAULT 'replit',
        status VARCHAR(32) NOT NULL DEFAULT 'offline',
        current_task_id VARCHAR(64),
        current_session_id VARCHAR(128),
        capabilities TEXT NOT NULL DEFAULT '[]',
        last_heartbeat TIMESTAMPTZ,
        last_checkin TIMESTAMPTZ,
        last_checkout TIMESTAMPTZ,
        checkin_summary TEXT NOT NULL DEFAULT '',
        checkout_summary TEXT NOT NULL DEFAULT '',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS agent_contracts (
        id SERIAL PRIMARY KEY,
        contract_name VARCHAR(128) UNIQUE NOT NULL,
        contract_text TEXT NOT NULL,
        category VARCHAR(64) NOT NULL DEFAULT 'architecture',
        enforced BOOLEAN NOT NULL DEFAULT TRUE,
        violation_action VARCHAR(64) NOT NULL DEFAULT 'block',
        source VARCHAR(128) NOT NULL DEFAULT 'system',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS swarm_dispatch (
        id SERIAL PRIMARY KEY,
        sprint_id INTEGER,
        task_id VARCHAR(64) NOT NULL,
        assigned_worker_id VARCHAR(128),
        assigned_role VARCHAR(64) NOT NULL DEFAULT 'line_worker',
        status VARCHAR(32) NOT NULL DEFAULT 'queued',
        priority INTEGER NOT NULL DEFAULT 3,
        claimed_at TIMESTAMPTZ,
        started_at TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,
        result TEXT NOT NULL DEFAULT '',
        error TEXT NOT NULL DEFAULT '',
        retries INTEGER NOT NULL DEFAULT 0,
        max_retries INTEGER NOT NULL DEFAULT 2,
        timeout_seconds INTEGER NOT NULL DEFAULT 300,
        parent_dispatch_id INTEGER REFERENCES swarm_dispatch(id),
        escalated_from VARCHAR(128),
        escalated_reason TEXT NOT NULL DEFAULT '',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS swarm_messages (
        id SERIAL PRIMARY KEY,
        from_worker_id VARCHAR(128) NOT NULL,
        to_worker_id VARCHAR(128) NOT NULL DEFAULT '*',
        channel VARCHAR(64) NOT NULL DEFAULT 'broadcast',
        message_type VARCHAR(32) NOT NULL DEFAULT 'info',
        subject VARCHAR(256) NOT NULL DEFAULT '',
        body TEXT NOT NULL DEFAULT '',
        ref_task_id VARCHAR(64),
        ref_dispatch_id INTEGER,
        acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
        ack_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS swarm_sprints (
        id SERIAL PRIMARY KEY,
        name VARCHAR(256) NOT NULL,
        goal TEXT NOT NULL DEFAULT '',
        status VARCHAR(32) NOT NULL DEFAULT 'planning',
        strategy VARCHAR(64) NOT NULL DEFAULT 'parallel',
        max_concurrent_workers INTEGER NOT NULL DEFAULT 10,
        task_filter JSONB NOT NULL DEFAULT '{}',
        total_tasks INTEGER NOT NULL DEFAULT 0,
        completed_tasks INTEGER NOT NULL DEFAULT 0,
        failed_tasks INTEGER NOT NULL DEFAULT 0,
        started_at TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        summary TEXT NOT NULL DEFAULT ''
    );
    """)
    conn.commit()
    conn.close()
    print("SIRM tables initialized.")

if __name__ == "__main__":
    init_tables()
