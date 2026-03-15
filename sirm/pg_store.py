import json
import os
import logging
from typing import Optional
from contextlib import contextmanager
import psycopg2
import psycopg2.extras
from sirm.models import (
    WorkOrder, MemoryEntry, QualityGate, Session, FactoryConfig, ForgeItem,
    _now, _new_id
)

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")

PG_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sirm_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sirm_tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'backlog',
    stage TEXT NOT NULL DEFAULT 'plan',
    role TEXT NOT NULL DEFAULT 'line_worker',
    assigned_to TEXT NOT NULL DEFAULT '',
    priority INTEGER NOT NULL DEFAULT 3,
    acceptance_criteria TEXT NOT NULL DEFAULT '[]',
    dependencies TEXT NOT NULL DEFAULT '[]',
    security_considerations TEXT NOT NULL DEFAULT '',
    evidence TEXT NOT NULL DEFAULT '[]',
    tags TEXT NOT NULL DEFAULT '[]',
    activity_log TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sirm_memories (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL DEFAULT 'discovery',
    content TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sirm_gates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    stage TEXT NOT NULL DEFAULT 'code',
    gate_type TEXT NOT NULL DEFAULT 'manual',
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'not_run',
    last_run TEXT NOT NULL DEFAULT '',
    evidence TEXT NOT NULL DEFAULT '',
    command TEXT NOT NULL DEFAULT '',
    last_output TEXT NOT NULL DEFAULT '',
    last_exit_code INTEGER DEFAULT NULL,
    run_count INTEGER NOT NULL DEFAULT 0,
    execution_history TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS sirm_sessions (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL DEFAULT '',
    worker TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'line_worker',
    tasks_worked TEXT NOT NULL DEFAULT '[]',
    notes TEXT NOT NULL DEFAULT '',
    baton_pass TEXT NOT NULL DEFAULT '{}',
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS sirm_forge_items (
    id TEXT PRIMARY KEY,
    raw_input TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'manual',
    status TEXT NOT NULL DEFAULT 'raw',
    extracted_title TEXT NOT NULL DEFAULT '',
    extracted_description TEXT NOT NULL DEFAULT '',
    extracted_type TEXT NOT NULL DEFAULT 'unknown',
    suggested_priority INTEGER NOT NULL DEFAULT 3,
    suggested_role TEXT NOT NULL DEFAULT 'line_worker',
    suggested_stage TEXT NOT NULL DEFAULT 'plan',
    suggested_tags TEXT NOT NULL DEFAULT '[]',
    suggested_product_line TEXT NOT NULL DEFAULT '',
    suggested_project TEXT NOT NULL DEFAULT '',
    confidence_score INTEGER NOT NULL DEFAULT 0,
    gate_results TEXT NOT NULL DEFAULT '[]',
    gate_score INTEGER NOT NULL DEFAULT 0,
    related_existing TEXT NOT NULL DEFAULT '[]',
    extraction_notes TEXT NOT NULL DEFAULT '[]',
    work_order_id TEXT NOT NULL DEFAULT '',
    rejection_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON sirm_tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_stage ON sirm_tasks(stage);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON sirm_tasks(priority);
CREATE INDEX IF NOT EXISTS idx_memories_category ON sirm_memories(category);
CREATE INDEX IF NOT EXISTS idx_gates_stage ON sirm_gates(stage);
CREATE INDEX IF NOT EXISTS idx_sessions_active ON sirm_sessions(active);
CREATE INDEX IF NOT EXISTS idx_forge_status ON sirm_forge_items(status);
"""


def _get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn


@contextmanager
def _db():
    conn = _get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_pg_schema():
    with _db() as conn:
        cur = conn.cursor()
        cur.execute(PG_SCHEMA_SQL)
    logger.info("PostgreSQL SIRM schema initialized")


class PostgresStore:
    def __init__(self):
        init_pg_schema()

    def get_config(self) -> FactoryConfig:
        with _db() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute("SELECT value FROM sirm_config WHERE key = 'factory'")
            row = cur.fetchone()
        if row:
            return FactoryConfig.from_dict(json.loads(row["value"]))
        return FactoryConfig()

    def save_config(self, config: FactoryConfig):
        with _db() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO sirm_config (key, value) VALUES ('factory', %s)
                   ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
                (json.dumps(config.to_dict(), default=str),)
            )

    def init_factory(self, name: str = "SIRM Factory", description: str = "") -> FactoryConfig:
        config = FactoryConfig(name=name, description=description)
        self.save_config(config)
        default_gates = [
            QualityGate(name="Unit Tests", stage="code", gate_type="automated",
                        description="Run unit test suite"),
            QualityGate(name="Linting", stage="code", gate_type="automated",
                        description="Static analysis and code style"),
            QualityGate(name="Secrets Detection", stage="code", gate_type="automated",
                        description="Scan for exposed secrets"),
            QualityGate(name="Dependency Scan", stage="build", gate_type="automated",
                        description="Check dependencies for known vulnerabilities"),
            QualityGate(name="Code Review", stage="integrate", gate_type="manual",
                        description="Peer review of changes"),
            QualityGate(name="Security Review", stage="release", gate_type="manual",
                        description="Security assessment before release"),
        ]
        for gate in default_gates:
            self.save_gate(gate)
        return config

    def list_tasks(self, status: Optional[str] = None, stage: Optional[str] = None,
                   role: Optional[str] = None, priority: Optional[int] = None) -> list[WorkOrder]:
        with _db() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            query = "SELECT * FROM sirm_tasks WHERE TRUE"
            params = []
            if status:
                query += " AND status = %s"
                params.append(status)
            if stage:
                query += " AND stage = %s"
                params.append(stage)
            if role:
                query += " AND role = %s"
                params.append(role)
            if priority is not None:
                query += " AND priority = %s"
                params.append(priority)
            query += " ORDER BY id"
            cur.execute(query, params)
            rows = cur.fetchall()
        return [self._row_to_task(r) for r in rows]

    def _row_to_task(self, row) -> WorkOrder:
        return WorkOrder(
            id=row["id"], title=row["title"], description=row["description"],
            status=row["status"], stage=row["stage"], role=row["role"],
            assigned_to=row["assigned_to"], priority=row["priority"],
            acceptance_criteria=json.loads(row["acceptance_criteria"]),
            dependencies=json.loads(row["dependencies"]),
            security_considerations=row["security_considerations"],
            evidence=json.loads(row["evidence"]),
            tags=json.loads(row["tags"]),
            activity_log=json.loads(row["activity_log"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def get_task(self, task_id: str) -> Optional[WorkOrder]:
        with _db() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute("SELECT * FROM sirm_tasks WHERE id = %s", (task_id,))
            row = cur.fetchone()
        return self._row_to_task(row) if row else None

    def save_task(self, task: WorkOrder):
        task.updated_at = _now()
        with _db() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO sirm_tasks
                   (id, title, description, status, stage, role, assigned_to, priority,
                    acceptance_criteria, dependencies, security_considerations, evidence,
                    tags, activity_log, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (id) DO UPDATE SET
                    title=EXCLUDED.title, description=EXCLUDED.description,
                    status=EXCLUDED.status, stage=EXCLUDED.stage, role=EXCLUDED.role,
                    assigned_to=EXCLUDED.assigned_to, priority=EXCLUDED.priority,
                    acceptance_criteria=EXCLUDED.acceptance_criteria,
                    dependencies=EXCLUDED.dependencies,
                    security_considerations=EXCLUDED.security_considerations,
                    evidence=EXCLUDED.evidence, tags=EXCLUDED.tags,
                    activity_log=EXCLUDED.activity_log, updated_at=EXCLUDED.updated_at""",
                (task.id, task.title, task.description, task.status, task.stage,
                 task.role, task.assigned_to, task.priority,
                 json.dumps(task.acceptance_criteria), json.dumps(task.dependencies),
                 task.security_considerations, json.dumps(task.evidence, default=str),
                 json.dumps(task.tags), json.dumps(task.activity_log, default=str),
                 task.created_at, task.updated_at)
            )

    def delete_task(self, task_id: str):
        with _db() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM sirm_tasks WHERE id = %s", (task_id,))

    def list_memories(self, category: Optional[str] = None) -> list[MemoryEntry]:
        with _db() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            query = "SELECT * FROM sirm_memories"
            params = []
            if category:
                query += " WHERE category = %s"
                params.append(category)
            query += " ORDER BY created_at DESC"
            cur.execute(query, params)
            rows = cur.fetchall()
        return [self._row_to_memory(r) for r in rows]

    def _row_to_memory(self, row) -> MemoryEntry:
        return MemoryEntry(
            id=row["id"], category=row["category"], content=row["content"],
            source=row["source"], tags=json.loads(row["tags"]),
            created_at=row["created_at"],
        )

    def get_memory(self, mem_id: str) -> Optional[MemoryEntry]:
        with _db() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute("SELECT * FROM sirm_memories WHERE id = %s", (mem_id,))
            row = cur.fetchone()
        return self._row_to_memory(row) if row else None

    def save_memory(self, entry: MemoryEntry):
        with _db() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO sirm_memories (id, category, content, source, tags, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (id) DO UPDATE SET
                    category=EXCLUDED.category, content=EXCLUDED.content,
                    source=EXCLUDED.source, tags=EXCLUDED.tags""",
                (entry.id, entry.category, entry.content, entry.source,
                 json.dumps(entry.tags), entry.created_at)
            )

    def delete_memory(self, mem_id: str):
        with _db() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM sirm_memories WHERE id = %s", (mem_id,))

    def list_gates(self, stage: Optional[str] = None) -> list[QualityGate]:
        with _db() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            query = "SELECT * FROM sirm_gates"
            params = []
            if stage:
                query += " WHERE stage = %s"
                params.append(stage)
            query += " ORDER BY id"
            cur.execute(query, params)
            rows = cur.fetchall()
        return [self._row_to_gate(r) for r in rows]

    def _row_to_gate(self, row) -> QualityGate:
        return QualityGate(
            id=row["id"], name=row["name"], stage=row["stage"],
            gate_type=row["gate_type"], description=row["description"],
            status=row["status"], last_run=row["last_run"],
            evidence=row["evidence"], command=row["command"],
            last_output=row.get("last_output", ""),
            last_exit_code=row.get("last_exit_code"),
            run_count=row.get("run_count", 0) or 0,
            execution_history=json.loads(row.get("execution_history", "[]")),
        )

    def get_gate(self, gate_id: str) -> Optional[QualityGate]:
        with _db() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute("SELECT * FROM sirm_gates WHERE id = %s", (gate_id,))
            row = cur.fetchone()
        return self._row_to_gate(row) if row else None

    def save_gate(self, gate: QualityGate):
        with _db() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO sirm_gates
                   (id, name, stage, gate_type, description, status, last_run, evidence,
                    command, last_output, last_exit_code, run_count, execution_history)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (id) DO UPDATE SET
                    name=EXCLUDED.name, stage=EXCLUDED.stage, gate_type=EXCLUDED.gate_type,
                    description=EXCLUDED.description, status=EXCLUDED.status,
                    last_run=EXCLUDED.last_run, evidence=EXCLUDED.evidence,
                    command=EXCLUDED.command, last_output=EXCLUDED.last_output,
                    last_exit_code=EXCLUDED.last_exit_code, run_count=EXCLUDED.run_count,
                    execution_history=EXCLUDED.execution_history""",
                (gate.id, gate.name, gate.stage, gate.gate_type, gate.description,
                 gate.status, gate.last_run, gate.evidence, gate.command,
                 getattr(gate, 'last_output', ''),
                 getattr(gate, 'last_exit_code', None),
                 getattr(gate, 'run_count', 0) or 0,
                 json.dumps(getattr(gate, 'execution_history', []), default=str))
            )

    def delete_gate(self, gate_id: str):
        with _db() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM sirm_gates WHERE id = %s", (gate_id,))

    def list_sessions(self) -> list[Session]:
        with _db() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute("SELECT * FROM sirm_sessions ORDER BY started_at DESC")
            rows = cur.fetchall()
        return [self._row_to_session(r) for r in rows]

    def _row_to_session(self, row) -> Session:
        return Session(
            id=row["id"], started_at=row["started_at"], ended_at=row["ended_at"],
            worker=row["worker"], role=row["role"],
            tasks_worked=json.loads(row["tasks_worked"]),
            notes=row["notes"], baton_pass=json.loads(row["baton_pass"]),
            active=bool(row["active"]),
        )

    def get_session(self, session_id: str) -> Optional[Session]:
        with _db() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute("SELECT * FROM sirm_sessions WHERE id = %s", (session_id,))
            row = cur.fetchone()
        return self._row_to_session(row) if row else None

    def get_active_session(self) -> Optional[Session]:
        with _db() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute("SELECT * FROM sirm_sessions WHERE active = TRUE ORDER BY started_at DESC LIMIT 1")
            row = cur.fetchone()
        return self._row_to_session(row) if row else None

    def save_session(self, session: Session):
        with _db() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO sirm_sessions
                   (id, started_at, ended_at, worker, role, tasks_worked, notes, baton_pass, active)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (id) DO UPDATE SET
                    ended_at=EXCLUDED.ended_at, worker=EXCLUDED.worker, role=EXCLUDED.role,
                    tasks_worked=EXCLUDED.tasks_worked, notes=EXCLUDED.notes,
                    baton_pass=EXCLUDED.baton_pass, active=EXCLUDED.active""",
                (session.id, session.started_at, session.ended_at, session.worker,
                 session.role, json.dumps(session.tasks_worked),
                 session.notes, json.dumps(session.baton_pass, default=str),
                 session.active)
            )

    def start_session(self, worker: str = "", role: str = "line_worker") -> Session:
        active = self.get_active_session()
        if active:
            active.active = False
            active.ended_at = _now()
            self.save_session(active)
        session = Session(worker=worker, role=role)
        self.save_session(session)
        return session

    def end_session(self, session_id: str, baton_pass: dict = None) -> Optional[Session]:
        session = self.get_session(session_id)
        if session:
            session.active = False
            session.ended_at = _now()
            if baton_pass:
                session.baton_pass = baton_pass
            self.save_session(session)
        return session

    def check_stage_gates(self, stage: str) -> dict:
        gates = self.list_gates(stage=stage)
        if not gates:
            return {"passed": True, "failing": [], "not_run": [], "gates": []}
        failing = [g for g in gates if g.status == "failing"]
        not_run = [g for g in gates if g.status == "not_run"]
        passed = len(failing) == 0 and len(not_run) == 0
        return {"passed": passed, "failing": failing, "not_run": not_run, "gates": gates}

    def _row_to_forge_item(self, row) -> ForgeItem:
        return ForgeItem(
            id=row["id"], raw_input=row["raw_input"], source=row["source"],
            status=row["status"], extracted_title=row["extracted_title"],
            extracted_description=row["extracted_description"],
            extracted_type=row["extracted_type"],
            suggested_priority=row["suggested_priority"],
            suggested_role=row["suggested_role"],
            suggested_stage=row["suggested_stage"],
            suggested_tags=json.loads(row["suggested_tags"]),
            suggested_product_line=row["suggested_product_line"],
            suggested_project=row["suggested_project"],
            confidence_score=row["confidence_score"],
            gate_results=json.loads(row["gate_results"]),
            gate_score=row["gate_score"],
            related_existing=json.loads(row["related_existing"]),
            extraction_notes=json.loads(row["extraction_notes"]),
            work_order_id=row["work_order_id"],
            rejection_reason=row["rejection_reason"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def list_forge_items(self, status: Optional[str] = None) -> list[ForgeItem]:
        with _db() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            query = "SELECT * FROM sirm_forge_items"
            params = []
            if status:
                query += " WHERE status = %s"
                params.append(status)
            query += " ORDER BY created_at DESC"
            cur.execute(query, params)
            rows = cur.fetchall()
        return [self._row_to_forge_item(r) for r in rows]

    def get_forge_item(self, item_id: str) -> Optional[ForgeItem]:
        with _db() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute("SELECT * FROM sirm_forge_items WHERE id = %s", (item_id,))
            row = cur.fetchone()
        return self._row_to_forge_item(row) if row else None

    def save_forge_item(self, item: ForgeItem):
        item.updated_at = _now()
        with _db() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO sirm_forge_items
                   (id, raw_input, source, status, extracted_title, extracted_description,
                    extracted_type, suggested_priority, suggested_role, suggested_stage,
                    suggested_tags, suggested_product_line, suggested_project,
                    confidence_score, gate_results, gate_score, related_existing,
                    extraction_notes, work_order_id, rejection_reason, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (id) DO UPDATE SET
                    raw_input=EXCLUDED.raw_input, source=EXCLUDED.source, status=EXCLUDED.status,
                    extracted_title=EXCLUDED.extracted_title,
                    extracted_description=EXCLUDED.extracted_description,
                    extracted_type=EXCLUDED.extracted_type,
                    suggested_priority=EXCLUDED.suggested_priority,
                    suggested_role=EXCLUDED.suggested_role,
                    suggested_stage=EXCLUDED.suggested_stage,
                    suggested_tags=EXCLUDED.suggested_tags,
                    suggested_product_line=EXCLUDED.suggested_product_line,
                    suggested_project=EXCLUDED.suggested_project,
                    confidence_score=EXCLUDED.confidence_score,
                    gate_results=EXCLUDED.gate_results, gate_score=EXCLUDED.gate_score,
                    related_existing=EXCLUDED.related_existing,
                    extraction_notes=EXCLUDED.extraction_notes,
                    work_order_id=EXCLUDED.work_order_id,
                    rejection_reason=EXCLUDED.rejection_reason,
                    updated_at=EXCLUDED.updated_at""",
                (item.id, item.raw_input, item.source, item.status,
                 item.extracted_title, item.extracted_description, item.extracted_type,
                 item.suggested_priority, item.suggested_role, item.suggested_stage,
                 json.dumps(item.suggested_tags), item.suggested_product_line,
                 item.suggested_project, item.confidence_score,
                 json.dumps(item.gate_results, default=str), item.gate_score,
                 json.dumps(item.related_existing, default=str),
                 json.dumps(item.extraction_notes, default=str),
                 item.work_order_id, item.rejection_reason,
                 item.created_at, item.updated_at)
            )

    def delete_forge_item(self, item_id: str):
        with _db() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM sirm_forge_items WHERE id = %s", (item_id,))

    def search(self, query: str) -> dict:
        query_lower = query.lower().strip()
        if not query_lower:
            return {"tasks": [], "memories": [], "gates": []}
        matched_tasks = [t for t in self.list_tasks()
                         if query_lower in " ".join([t.title, t.description, t.id, t.status,
                                                      t.stage, t.role, t.assigned_to,
                                                      t.security_considerations,
                                                      " ".join(t.tags),
                                                      " ".join(t.acceptance_criteria)]).lower()]
        matched_memories = [m for m in self.list_memories()
                            if query_lower in " ".join([m.content, m.source, m.category, m.id,
                                                         " ".join(m.tags)]).lower()]
        matched_gates = [g for g in self.list_gates()
                         if query_lower in " ".join([g.name, g.description, g.stage,
                                                      g.gate_type, g.status, g.id]).lower()]
        return {"tasks": matched_tasks, "memories": matched_memories, "gates": matched_gates}

    def get_radiator_state(self) -> dict:
        config = self.get_config()
        tasks = self.list_tasks()
        active_session = self.get_active_session()
        gates = self.list_gates()
        memories = self.list_memories()
        sessions = self.list_sessions()

        task_counts = {}
        for status in ["backlog", "ready", "in_progress", "verification", "done", "blocked"]:
            task_counts[status] = len([t for t in tasks if t.status == status])

        stage_counts = {}
        for stage in ["plan", "code", "build", "integrate", "release", "operate"]:
            stage_counts[stage] = len([t for t in tasks if t.stage == stage and t.status != "done"])

        gate_summary = {}
        for status in ["passing", "failing", "not_run", "skipped"]:
            gate_summary[status] = len([g for g in gates if g.status == status])

        wip_tasks = [t.to_dict() for t in tasks if t.status == "in_progress"]
        blocked_tasks = [t.to_dict() for t in tasks if t.status == "blocked"]
        ready_tasks = [t.to_dict() for t in tasks if t.status == "ready"]
        verification_tasks = [t.to_dict() for t in tasks if t.status == "verification"]
        recent_memories = [m.to_dict() for m in memories[:5]]

        last_baton = None
        for s in sessions:
            if not s.active and s.baton_pass:
                last_baton = s.baton_pass
                break

        total_gates = len(gates)
        gate_pass_rate = (gate_summary["passing"] / total_gates * 100) if total_gates else 100
        total_tasks_count = len(tasks)
        if total_tasks_count > 0:
            done_count = task_counts["done"]
            blocked_count = task_counts["blocked"]
            completion_rate = (done_count / total_tasks_count) * 100
            blocked_ratio = (blocked_count / total_tasks_count) * 100
        else:
            completion_rate = 0
            blocked_ratio = 0

        memory_coverage = min(len(memories) * 10, 100)
        health_score = round(
            (gate_pass_rate * 0.35) + (completion_rate * 0.25) +
            ((100 - blocked_ratio) * 0.25) + (memory_coverage * 0.15)
        )
        health_score = max(0, min(100, health_score))

        stage_progress = {}
        for stage_name in ["plan", "code", "build", "integrate", "release", "operate"]:
            stage_total = len([t for t in tasks if t.stage == stage_name])
            stage_done = len([t for t in tasks if t.stage == stage_name and t.status == "done"])
            stage_progress[stage_name] = {
                "total": stage_total, "done": stage_done,
                "active": stage_counts[stage_name],
                "percent": round((stage_done / stage_total) * 100) if stage_total > 0 else 0,
            }

        return {
            "factory": config.to_dict(),
            "active_session": active_session.to_dict() if active_session else None,
            "task_counts": task_counts, "stage_counts": stage_counts,
            "total_tasks": len(tasks),
            "wip_tasks": wip_tasks, "blocked_tasks": blocked_tasks,
            "ready_tasks": ready_tasks, "verification_tasks": verification_tasks,
            "gate_summary": gate_summary,
            "gates": [g.to_dict() for g in gates],
            "recent_memories": recent_memories,
            "last_baton_pass": last_baton,
            "session_count": len(sessions),
            "health_score": health_score,
            "gate_pass_rate": round(gate_pass_rate),
            "completion_rate": round(completion_rate),
            "blocked_ratio": round(blocked_ratio),
            "memory_coverage": round(memory_coverage),
            "stage_progress": stage_progress,
        }
