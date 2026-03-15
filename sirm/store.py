import json
import os
from pathlib import Path
from typing import Optional
from sirm.models import (
    WorkOrder, MemoryEntry, QualityGate, Session, FactoryConfig,
    _now, _new_id
)

DATA_DIR = Path(".sirm")


def _ensure_dirs():
    DATA_DIR.mkdir(exist_ok=True)
    for sub in ["tasks", "memory", "gates", "sessions"]:
        (DATA_DIR / sub).mkdir(exist_ok=True)


def _load_json(path: Path, default=None):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default if default is not None else {}


def _save_json(path: Path, data):
    _ensure_dirs()
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


class SIRMStore:
    def __init__(self, base_path: str = "."):
        self.base = Path(base_path)
        self.data_dir = self.base / ".sirm"
        _ensure_dirs()

    def _path(self, *parts):
        return self.data_dir.joinpath(*parts)

    def get_config(self) -> FactoryConfig:
        data = _load_json(self._path("config.json"), {})
        if data:
            return FactoryConfig.from_dict(data)
        return FactoryConfig()

    def save_config(self, config: FactoryConfig):
        _save_json(self._path("config.json"), config.to_dict())

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
        tasks_dir = self._path("tasks")
        tasks = []
        if tasks_dir.exists():
            for f in sorted(tasks_dir.glob("*.json")):
                data = _load_json(f)
                if data:
                    task = WorkOrder.from_dict(data)
                    if status and task.status != status:
                        continue
                    if stage and task.stage != stage:
                        continue
                    if role and task.role != role:
                        continue
                    if priority is not None and task.priority != priority:
                        continue
                    tasks.append(task)
        return tasks

    def get_task(self, task_id: str) -> Optional[WorkOrder]:
        path = self._path("tasks", f"{task_id}.json")
        data = _load_json(path)
        return WorkOrder.from_dict(data) if data else None

    def save_task(self, task: WorkOrder):
        task.updated_at = _now()
        _save_json(self._path("tasks", f"{task.id}.json"), task.to_dict())

    def delete_task(self, task_id: str):
        path = self._path("tasks", f"{task_id}.json")
        if path.exists():
            path.unlink()

    def list_memories(self, category: Optional[str] = None) -> list[MemoryEntry]:
        mem_dir = self._path("memory")
        entries = []
        if mem_dir.exists():
            for f in sorted(mem_dir.glob("*.json")):
                data = _load_json(f)
                if data:
                    entry = MemoryEntry.from_dict(data)
                    if category and entry.category != category:
                        continue
                    entries.append(entry)
        entries.sort(key=lambda e: e.created_at, reverse=True)
        return entries

    def get_memory(self, mem_id: str) -> Optional[MemoryEntry]:
        path = self._path("memory", f"{mem_id}.json")
        data = _load_json(path)
        return MemoryEntry.from_dict(data) if data else None

    def save_memory(self, entry: MemoryEntry):
        _save_json(self._path("memory", f"{entry.id}.json"), entry.to_dict())

    def delete_memory(self, mem_id: str):
        path = self._path("memory", f"{mem_id}.json")
        if path.exists():
            path.unlink()

    def list_gates(self, stage: Optional[str] = None) -> list[QualityGate]:
        gates_dir = self._path("gates")
        gates = []
        if gates_dir.exists():
            for f in sorted(gates_dir.glob("*.json")):
                data = _load_json(f)
                if data:
                    gate = QualityGate.from_dict(data)
                    if stage and gate.stage != stage:
                        continue
                    gates.append(gate)
        return gates

    def get_gate(self, gate_id: str) -> Optional[QualityGate]:
        path = self._path("gates", f"{gate_id}.json")
        data = _load_json(path)
        return QualityGate.from_dict(data) if data else None

    def save_gate(self, gate: QualityGate):
        _save_json(self._path("gates", f"{gate.id}.json"), gate.to_dict())

    def delete_gate(self, gate_id: str):
        path = self._path("gates", f"{gate_id}.json")
        if path.exists():
            path.unlink()

    def list_sessions(self) -> list[Session]:
        sess_dir = self._path("sessions")
        sessions = []
        if sess_dir.exists():
            for f in sorted(sess_dir.glob("*.json")):
                data = _load_json(f)
                if data:
                    sessions.append(Session.from_dict(data))
        sessions.sort(key=lambda s: s.started_at, reverse=True)
        return sessions

    def get_session(self, session_id: str) -> Optional[Session]:
        path = self._path("sessions", f"{session_id}.json")
        data = _load_json(path)
        return Session.from_dict(data) if data else None

    def get_active_session(self) -> Optional[Session]:
        for session in self.list_sessions():
            if session.active:
                return session
        return None

    def save_session(self, session: Session):
        _save_json(self._path("sessions", f"{session.id}.json"), session.to_dict())

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
