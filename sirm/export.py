"""
SIRM Export System — Extract SIRM as a standalone, vendor-agnostic framework.

SIRM (Secure Intelligent Release Management) is an open model architecture
for multi-agent software factory orchestration. This module exports the
core SIRM codebase from Orion into a clean, standalone package that can be:

  1. Forked and used independently of Orion
  2. Published as a white paper reference implementation
  3. Presented at conferences with clean, readable code
  4. Deployed on any platform with any LLM provider

Usage:
  python -m sirm.export --output ./sirm-standalone
  python -m sirm.export --output ./sirm-standalone --include-data
"""

import os
import shutil
import json
from pathlib import Path
from datetime import datetime, timezone

SIRM_CORE_FILES = [
    "sirm/__init__.py",
    "sirm/models.py",
    "sirm/pipeline.py",
    "sirm/swarm.py",
    "sirm/central_api.py",
    "sirm/agent_memory.py",
    "sirm/triage.py",
    "sirm/templates_engine.py",
    "sirm/radiator.py",
    "sirm/sprint_engine.py",
    "sirm/foundry.py",
    "sirm/orchestration.py",
    "sirm/agent_context.py",
    "sirm/pg_store.py",
    "sirm/db.py",
    "sirm/store.py",
    "sirm/linear_client.py",
    "sirm/linear_sync.py",
    "sirm/export.py",
]

SIRM_DOCS = [
    "docs/sirm_g0_g7.md",
    "docs/agent_coordination.md",
    "docs/vision.md",
    "docs/product_bootstrap_template.md",
    "docs/identity-secrets-integration.md",
]

SIRM_AGENT_SKILLS = [
    ".agents/skills/sirm-factory/SKILL.md",
    ".agents/skills/sirm-pipeline/SKILL.md",
]

SIRM_TEMPLATES = [
    "templates/sprint_command.html",
    "templates/tasks.html",
    "templates/task_form.html",
    "templates/task_detail.html",
    "templates/memory.html",
    "templates/memory_form.html",
    "templates/gates.html",
    "templates/gate_form.html",
    "templates/gate_detail.html",
    "templates/sessions.html",
    "templates/session_end.html",
    "templates/factory.html",
    "templates/roadmap.html",
    "templates/foundry.html",
    "templates/foundry_detail.html",
    "templates/foundry_intake.html",
    "templates/orchestration.html",
    "templates/project_detail.html",
    "templates/base.html",
    "templates/search.html",
    "templates/dashboard.html",
]

STANDALONE_README = """# SIRM — Secure Intelligent Release Management

A multi-agent software factory orchestration framework.

## What Is SIRM?

SIRM is a model architecture for coordinating autonomous AI agents in a
hierarchical software factory. It provides:

- **Factory Hierarchy**: Plant Governance → Factory Manager → Assembly Manager → Line Manager → Line Worker → Quality Overlay
- **Swarm Orchestration**: Deploy N agents simultaneously against a task queue with role-based dispatch, heartbeat monitoring, and automatic reassignment
- **Sprint Execution**: Define a sprint, filter tasks, launch — the swarm controller fans work out to available agents and tracks velocity in real time
- **Escalation Chains**: When a line worker hits a blocker, the task escalates up the hierarchy automatically with context preservation
- **Quality Gates**: G0-G7 gate model (plan→code→build→integrate→release→operate→ship→audit) with enforcement — tasks cannot advance without passing gates
- **Inter-Agent Communication**: Message bus with channels, acknowledgment, broadcast, and directed messaging between any agents in the swarm
- **Persistent Memory**: Decisions, discoveries, architecture notes, and session baton passes survive across all agents, all sessions, all environments
- **Central API**: Single authenticated HTTP API that every agent (local, cloud, CI/CD) calls — one database, one source of truth

## Architecture

```
SIRM Factory
├── Central API (sirm/central_api.py)     — HTTP control plane for all agents
├── Swarm Controller (sirm/swarm.py)      — Multi-agent dispatch, escalation, sprints
├── Agent Memory (sirm/agent_memory.py)   — Persistent cross-session context
├── Pipeline Engine (sirm/pipeline.py)    — Stage advancement + gate enforcement
├── Triage Engine (sirm/triage.py)        — Automated task classification + routing
├── Forge (sirm/foundry.py)              — Idea intake → structured work orders
├── Sprint Engine (sirm/sprint_engine.py) — Real-time auto-prompts + velocity
├── Orchestration (sirm/orchestration.py) — Cross-product factory dashboard
├── Models (sirm/models.py)              — WorkOrder, MemoryEntry, QualityGate, Session
├── PostgreSQL Store (sirm/pg_store.py)  — Production data store
├── Radiator (sirm/radiator.py)          — Terminal + text-format status output
└── Export (sirm/export.py)              — This: extract SIRM as standalone package
```

## Role Hierarchy

| Role | Authority | Can Dispatch | Can Review | Escalates To | Max Concurrent |
|------|-----------|-------------|------------|--------------|----------------|
| line_worker | Execute tasks | No | No | line_manager | 1 |
| quality_overlay | Execute + review | No | Yes | assembly_manager | 3 |
| line_manager | Execute + review + dispatch | Yes | Yes | assembly_manager | 2 |
| assembly_manager | Full + gate override | Yes | Yes | factory_manager | 5 |
| factory_manager | Full + gate override | Yes | Yes | plant_governance | 10 |
| plant_governance | Policy only | Yes | Yes | — | 0 |

## Swarm Flow

```
1. CREATE SPRINT          → Define goal, filter tasks, set strategy
2. LAUNCH                 → Fan out tasks to swarm_dispatch queue
3. DISPATCH               → Controller assigns tasks to workers by role + load
4. WORKER CLAIMS          → Atomic claim prevents collision
5. WORKER EXECUTES        → Reports heartbeat, logs progress
6. ESCALATE (if blocked)  → Task moves up hierarchy with context
7. COMPLETE/FAIL          → Result recorded, sprint progress updated
8. MONITOR                → Controller detects stale workers, reassigns
9. SPRINT COMPLETES       → All tasks done/failed, velocity calculated
```

## Quick Start

```bash
# Set up PostgreSQL
export DATABASE_URL="postgresql://user:pass@host:5432/sirm"

# Initialize tables
python -m sirm.setup

# Run the API server
python app.py

# Or integrate into your own Flask app:
from sirm.central_api import central_bp
app.register_blueprint(central_bp)
```

## API Authentication

Set `SIRM_API_KEY` environment variable. All requests require `X-API-Key` header.

```bash
curl -H "X-API-Key: $SIRM_API_KEY" http://localhost:5000/api/sirm/briefing
```

## Vendor Agnostic

SIRM does not depend on any specific LLM provider. The framework handles
orchestration, dispatch, and coordination — your agents bring their own
intelligence. Works with Claude, GPT, Gemini, Llama, or any other model.

## License

Proprietary — Brush Cyber, LLC. Contact: douglas@brushcyber.com
"""

STANDALONE_REQUIREMENTS = """psycopg2-binary>=2.9.0
flask>=3.0.0
gunicorn>=21.2.0
"""

STANDALONE_SETUP_PY = '''"""SIRM — Secure Intelligent Release Management"""
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
'''

STANDALONE_APP = """import os
from flask import Flask
from sirm.central_api import central_bp

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))
app.register_blueprint(central_bp)

@app.route("/health")
def health():
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
"""

STANDALONE_MAKEFILE = """
.PHONY: setup run export clean

setup:
\tpip install -r requirements.txt
\tpython setup_db.py

run:
\tgunicorn --bind 0.0.0.0:5000 --reload app:app

export:
\tpython -m sirm.export --output ./sirm-export

clean:
\trm -rf __pycache__ sirm/__pycache__
"""


def export_sirm(output_dir: str, include_data: bool = False, include_templates: bool = True,
                include_docs: bool = True, source_root: str = "."):
    output = Path(output_dir)
    source = Path(source_root)

    if output.exists():
        shutil.rmtree(output)

    output.mkdir(parents=True)
    (output / "sirm").mkdir()

    copied = {"core": 0, "docs": 0, "templates": 0, "skills": 0}

    for f in SIRM_CORE_FILES:
        src = source / f
        if src.exists():
            dst = output / f
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied["core"] += 1

    if include_docs:
        (output / "docs").mkdir(exist_ok=True)
        for f in SIRM_DOCS:
            src = source / f
            if src.exists():
                dst = output / f
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied["docs"] += 1

        for f in SIRM_AGENT_SKILLS:
            src = source / f
            if src.exists():
                dst = output / f
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied["skills"] += 1

    if include_templates:
        for f in SIRM_TEMPLATES:
            src = source / f
            if src.exists():
                dst = output / f
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied["templates"] += 1

    (output / "README.md").write_text(STANDALONE_README)
    (output / "requirements.txt").write_text(STANDALONE_REQUIREMENTS.strip() + "\n")
    (output / "setup_db.py").write_text(STANDALONE_SETUP_PY)
    (output / "app.py").write_text(STANDALONE_APP)
    (output / "Makefile").write_text(STANDALONE_MAKEFILE.strip() + "\n")

    manifest = {
        "name": "SIRM",
        "version": "1.0.0",
        "description": "Secure Intelligent Release Management — Multi-Agent Factory Orchestration",
        "author": "Brush Cyber, LLC",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "exported_from": "Orion Unified Management Plane",
        "files": copied,
        "includes_data": include_data,
        "includes_templates": include_templates,
        "includes_docs": include_docs,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2))

    if include_data:
        _export_data(output / "data")

    return manifest


def _export_data(data_dir: Path):
    data_dir.mkdir(parents=True, exist_ok=True)
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        (data_dir / "NOTE.md").write_text("No DATABASE_URL set. Data export skipped.\n")
        return

    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(db_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    tables = [
        "agent_contracts", "agent_directives", "agent_context",
    ]
    for table in tables:
        try:
            cur.execute(f"SELECT * FROM {table}")
            rows = [dict(r) for r in cur.fetchall()]
            (data_dir / f"{table}.json").write_text(json.dumps(rows, indent=2, default=str))
        except Exception as e:
            print(f"Warning: could not export {table}: {e}")
            conn.rollback()

    conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Export SIRM as standalone package")
    parser.add_argument("--output", default="./sirm-standalone", help="Output directory")
    parser.add_argument("--include-data", action="store_true", help="Include contracts/directives/context data")
    parser.add_argument("--include-templates", action="store_true", default=True, help="Include Jinja2 templates")
    parser.add_argument("--no-templates", action="store_true", help="Exclude Jinja2 templates")
    parser.add_argument("--include-docs", action="store_true", default=True, help="Include documentation")
    parser.add_argument("--no-docs", action="store_true", help="Exclude documentation")
    args = parser.parse_args()

    include_templates = not args.no_templates
    include_docs = not args.no_docs

    result = export_sirm(
        args.output,
        include_data=args.include_data,
        include_templates=include_templates,
        include_docs=include_docs,
    )
    print(f"SIRM exported to {args.output}")
    print(f"  Core files: {result['files']['core']}")
    print(f"  Docs: {result['files']['docs']}")
    print(f"  Templates: {result['files']['templates']}")
    print(f"  Skills: {result['files']['skills']}")
    print(f"  Data included: {result['includes_data']}")
