import sqlite3
import json
import os
from pathlib import Path
from typing import Optional
from sirm.models import (
    WorkOrder, MemoryEntry, QualityGate, Session, FactoryConfig, ForgeItem,
    _now, _new_id
)

DB_PATH = os.environ.get("SIRM_DB_PATH", "sirm.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
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

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL DEFAULT 'discovery',
    content TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gates (
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

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL DEFAULT '',
    worker TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'line_worker',
    tasks_worked TEXT NOT NULL DEFAULT '[]',
    notes TEXT NOT NULL DEFAULT '',
    baton_pass TEXT NOT NULL DEFAULT '{}',
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS forge_items (
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
"""


def _get_conn(db_path=None):
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db(db_path=None):
    conn = _get_conn(db_path)
    conn.executescript(SCHEMA_SQL)
    _migrate_schema(conn)
    conn.commit()
    conn.close()


def _migrate_schema(conn):
    cursor = conn.execute("PRAGMA table_info(gates)")
    columns = {row[1] for row in cursor.fetchall()}
    migrations = [
        ("last_output", "ALTER TABLE gates ADD COLUMN last_output TEXT NOT NULL DEFAULT ''"),
        ("last_exit_code", "ALTER TABLE gates ADD COLUMN last_exit_code INTEGER DEFAULT NULL"),
        ("run_count", "ALTER TABLE gates ADD COLUMN run_count INTEGER NOT NULL DEFAULT 0"),
        ("execution_history", "ALTER TABLE gates ADD COLUMN execution_history TEXT NOT NULL DEFAULT '[]'"),
    ]
    for col_name, sql in migrations:
        if col_name not in columns:
            conn.execute(sql)


class SQLiteStore:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        _init_db(self.db_path)

    def _conn(self):
        return _get_conn(self.db_path)

    def get_config(self) -> FactoryConfig:
        conn = self._conn()
        row = conn.execute("SELECT value FROM config WHERE key = 'factory'").fetchone()
        conn.close()
        if row:
            return FactoryConfig.from_dict(json.loads(row["value"]))
        return FactoryConfig()

    def save_config(self, config: FactoryConfig):
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            ("factory", json.dumps(config.to_dict(), default=str))
        )
        conn.commit()
        conn.close()

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

    def _path(self, *parts):
        return Path(".sirm").joinpath(*parts)

    def list_tasks(self, status: Optional[str] = None, stage: Optional[str] = None,
                   role: Optional[str] = None, priority: Optional[int] = None) -> list[WorkOrder]:
        conn = self._conn()
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if stage:
            query += " AND stage = ?"
            params.append(stage)
        if role:
            query += " AND role = ?"
            params.append(role)
        if priority is not None:
            query += " AND priority = ?"
            params.append(priority)
        query += " ORDER BY id"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [self._row_to_task(r) for r in rows]

    def _row_to_task(self, row) -> WorkOrder:
        return WorkOrder(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            status=row["status"],
            stage=row["stage"],
            role=row["role"],
            assigned_to=row["assigned_to"],
            priority=row["priority"],
            acceptance_criteria=json.loads(row["acceptance_criteria"]),
            dependencies=json.loads(row["dependencies"]),
            security_considerations=row["security_considerations"],
            evidence=json.loads(row["evidence"]),
            tags=json.loads(row["tags"]),
            activity_log=json.loads(row["activity_log"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_task(self, task_id: str) -> Optional[WorkOrder]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        conn.close()
        return self._row_to_task(row) if row else None

    def save_task(self, task: WorkOrder):
        task.updated_at = _now()
        conn = self._conn()
        conn.execute(
            """INSERT OR REPLACE INTO tasks
               (id, title, description, status, stage, role, assigned_to, priority,
                acceptance_criteria, dependencies, security_considerations, evidence,
                tags, activity_log, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task.id, task.title, task.description, task.status, task.stage,
             task.role, task.assigned_to, task.priority,
             json.dumps(task.acceptance_criteria), json.dumps(task.dependencies),
             task.security_considerations, json.dumps(task.evidence, default=str),
             json.dumps(task.tags), json.dumps(task.activity_log, default=str),
             task.created_at, task.updated_at)
        )
        conn.commit()
        conn.close()

    def delete_task(self, task_id: str):
        conn = self._conn()
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
        conn.close()

    def list_memories(self, category: Optional[str] = None) -> list[MemoryEntry]:
        conn = self._conn()
        query = "SELECT * FROM memories"
        params = []
        if category:
            query += " WHERE category = ?"
            params.append(category)
        query += " ORDER BY created_at DESC"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [self._row_to_memory(r) for r in rows]

    def _row_to_memory(self, row) -> MemoryEntry:
        return MemoryEntry(
            id=row["id"],
            category=row["category"],
            content=row["content"],
            source=row["source"],
            tags=json.loads(row["tags"]),
            created_at=row["created_at"],
        )

    def get_memory(self, mem_id: str) -> Optional[MemoryEntry]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM memories WHERE id = ?", (mem_id,)).fetchone()
        conn.close()
        return self._row_to_memory(row) if row else None

    def save_memory(self, entry: MemoryEntry):
        conn = self._conn()
        conn.execute(
            """INSERT OR REPLACE INTO memories
               (id, category, content, source, tags, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (entry.id, entry.category, entry.content, entry.source,
             json.dumps(entry.tags), entry.created_at)
        )
        conn.commit()
        conn.close()

    def delete_memory(self, mem_id: str):
        conn = self._conn()
        conn.execute("DELETE FROM memories WHERE id = ?", (mem_id,))
        conn.commit()
        conn.close()

    def list_gates(self, stage: Optional[str] = None) -> list[QualityGate]:
        conn = self._conn()
        query = "SELECT * FROM gates"
        params = []
        if stage:
            query += " WHERE stage = ?"
            params.append(stage)
        query += " ORDER BY id"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [self._row_to_gate(r) for r in rows]

    def _row_to_gate(self, row) -> QualityGate:
        keys = row.keys()
        return QualityGate(
            id=row["id"],
            name=row["name"],
            stage=row["stage"],
            gate_type=row["gate_type"],
            description=row["description"],
            status=row["status"],
            last_run=row["last_run"],
            evidence=row["evidence"],
            command=row["command"],
            last_output=row["last_output"] if "last_output" in keys else "",
            last_exit_code=row["last_exit_code"] if "last_exit_code" in keys else None,
            run_count=row["run_count"] if "run_count" in keys else 0,
            execution_history=json.loads(row["execution_history"]) if "execution_history" in keys else [],
        )

    def get_gate(self, gate_id: str) -> Optional[QualityGate]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM gates WHERE id = ?", (gate_id,)).fetchone()
        conn.close()
        return self._row_to_gate(row) if row else None

    def save_gate(self, gate: QualityGate):
        conn = self._conn()
        conn.execute(
            """INSERT OR REPLACE INTO gates
               (id, name, stage, gate_type, description, status, last_run, evidence, command,
                last_output, last_exit_code, run_count, execution_history)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (gate.id, gate.name, gate.stage, gate.gate_type, gate.description,
             gate.status, gate.last_run, gate.evidence, gate.command,
             getattr(gate, 'last_output', ''),
             getattr(gate, 'last_exit_code', None),
             getattr(gate, 'run_count', 0) or 0,
             json.dumps(getattr(gate, 'execution_history', []), default=str))
        )
        conn.commit()
        conn.close()

    def delete_gate(self, gate_id: str):
        conn = self._conn()
        conn.execute("DELETE FROM gates WHERE id = ?", (gate_id,))
        conn.commit()
        conn.close()

    def list_sessions(self) -> list[Session]:
        conn = self._conn()
        rows = conn.execute("SELECT * FROM sessions ORDER BY started_at DESC").fetchall()
        conn.close()
        return [self._row_to_session(r) for r in rows]

    def _row_to_session(self, row) -> Session:
        return Session(
            id=row["id"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            worker=row["worker"],
            role=row["role"],
            tasks_worked=json.loads(row["tasks_worked"]),
            notes=row["notes"],
            baton_pass=json.loads(row["baton_pass"]),
            active=bool(row["active"]),
        )

    def get_session(self, session_id: str) -> Optional[Session]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        conn.close()
        return self._row_to_session(row) if row else None

    def get_active_session(self) -> Optional[Session]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM sessions WHERE active = 1 ORDER BY started_at DESC LIMIT 1").fetchone()
        conn.close()
        return self._row_to_session(row) if row else None

    def save_session(self, session: Session):
        conn = self._conn()
        conn.execute(
            """INSERT OR REPLACE INTO sessions
               (id, started_at, ended_at, worker, role, tasks_worked, notes, baton_pass, active)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session.id, session.started_at, session.ended_at, session.worker,
             session.role, json.dumps(session.tasks_worked),
             session.notes, json.dumps(session.baton_pass, default=str),
             1 if session.active else 0)
        )
        conn.commit()
        conn.close()

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
        return {
            "passed": passed,
            "failing": failing,
            "not_run": not_run,
            "gates": gates,
        }

    def _row_to_forge_item(self, row) -> ForgeItem:
        return ForgeItem(
            id=row["id"],
            raw_input=row["raw_input"],
            source=row["source"],
            status=row["status"],
            extracted_title=row["extracted_title"],
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
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_forge_items(self, status: Optional[str] = None) -> list[ForgeItem]:
        conn = self._conn()
        query = "SELECT * FROM forge_items"
        params = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [self._row_to_forge_item(r) for r in rows]

    def get_forge_item(self, item_id: str) -> Optional[ForgeItem]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM forge_items WHERE id = ?", (item_id,)).fetchone()
        conn.close()
        return self._row_to_forge_item(row) if row else None

    def save_forge_item(self, item: ForgeItem):
        item.updated_at = _now()
        conn = self._conn()
        conn.execute(
            """INSERT OR REPLACE INTO forge_items
               (id, raw_input, source, status, extracted_title, extracted_description,
                extracted_type, suggested_priority, suggested_role, suggested_stage,
                suggested_tags, suggested_product_line, suggested_project,
                confidence_score, gate_results, gate_score, related_existing,
                extraction_notes, work_order_id, rejection_reason, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
        conn.commit()
        conn.close()

    def delete_forge_item(self, item_id: str):
        conn = self._conn()
        conn.execute("DELETE FROM forge_items WHERE id = ?", (item_id,))
        conn.commit()
        conn.close()

    def search(self, query: str) -> dict:
        query_lower = query.lower().strip()
        if not query_lower:
            return {"tasks": [], "memories": [], "gates": []}

        matched_tasks = []
        for task in self.list_tasks():
            searchable = " ".join([
                task.title, task.description, task.id,
                task.status, task.stage, task.role,
                task.assigned_to, task.security_considerations,
                " ".join(task.tags),
                " ".join(task.acceptance_criteria),
            ]).lower()
            if query_lower in searchable:
                matched_tasks.append(task)

        matched_memories = []
        for mem in self.list_memories():
            searchable = " ".join([
                mem.content, mem.source, mem.category, mem.id,
                " ".join(mem.tags),
            ]).lower()
            if query_lower in searchable:
                matched_memories.append(mem)

        matched_gates = []
        for gate in self.list_gates():
            searchable = " ".join([
                gate.name, gate.description, gate.stage,
                gate.gate_type, gate.status, gate.id,
            ]).lower()
            if query_lower in searchable:
                matched_gates.append(gate)

        return {
            "tasks": matched_tasks,
            "memories": matched_memories,
            "gates": matched_gates,
        }

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
        if total_gates > 0:
            gate_pass_rate = (gate_summary["passing"] / total_gates) * 100
        else:
            gate_pass_rate = 100

        total_tasks_count = len(tasks)
        if total_tasks_count > 0:
            done_count = task_counts["done"]
            blocked_count = task_counts["blocked"]
            completion_rate = (done_count / total_tasks_count) * 100
            blocked_ratio = (blocked_count / total_tasks_count) * 100
        else:
            completion_rate = 0
            blocked_ratio = 0

        total_memories = len(memories)
        memory_coverage = min(total_memories * 10, 100)

        health_score = round(
            (gate_pass_rate * 0.35) +
            (completion_rate * 0.25) +
            ((100 - blocked_ratio) * 0.25) +
            (memory_coverage * 0.15)
        )
        health_score = max(0, min(100, health_score))

        stage_progress = {}
        for stage_name in ["plan", "code", "build", "integrate", "release", "operate"]:
            stage_total = len([t for t in tasks if t.stage == stage_name])
            stage_done = len([t for t in tasks if t.stage == stage_name and t.status == "done"])
            stage_progress[stage_name] = {
                "total": stage_total,
                "done": stage_done,
                "active": stage_counts[stage_name],
                "percent": round((stage_done / stage_total) * 100) if stage_total > 0 else 0,
            }

        return {
            "factory": config.to_dict(),
            "active_session": active_session.to_dict() if active_session else None,
            "task_counts": task_counts,
            "stage_counts": stage_counts,
            "total_tasks": len(tasks),
            "wip_tasks": wip_tasks,
            "blocked_tasks": blocked_tasks,
            "ready_tasks": ready_tasks,
            "verification_tasks": verification_tasks,
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


def migrate_json_to_sqlite(json_store, sqlite_store):
    migrated = {"tasks": 0, "memories": 0, "gates": 0, "sessions": 0, "config": False}

    config = json_store.get_config()
    if config.name:
        sqlite_store.save_config(config)
        migrated["config"] = True

    for task in json_store.list_tasks():
        sqlite_store.save_task(task)
        migrated["tasks"] += 1

    for mem in json_store.list_memories():
        sqlite_store.save_memory(mem)
        migrated["memories"] += 1

    for gate in json_store.list_gates():
        sqlite_store.save_gate(gate)
        migrated["gates"] += 1

    for session in json_store.list_sessions():
        sqlite_store.save_session(session)
        migrated["sessions"] += 1

    return migrated
