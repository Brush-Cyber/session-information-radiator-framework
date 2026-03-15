import uuid
import json
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Optional


class TaskStatus(str, Enum):
    BACKLOG = "backlog"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    VERIFICATION = "verification"
    DONE = "done"
    BLOCKED = "blocked"


class TaskStage(str, Enum):
    PLAN = "plan"
    CODE = "code"
    BUILD = "build"
    INTEGRATE = "integrate"
    RELEASE = "release"
    OPERATE = "operate"


class RoleType(str, Enum):
    PLANT_GOVERNANCE = "plant_governance"
    FACTORY_MANAGER = "factory_manager"
    ASSEMBLY_MANAGER = "assembly_manager"
    LINE_MANAGER = "line_manager"
    LINE_WORKER = "line_worker"
    QUALITY_OVERLAY = "quality_overlay"


class GateStatus(str, Enum):
    PASSING = "passing"
    FAILING = "failing"
    NOT_RUN = "not_run"
    SKIPPED = "skipped"


class MemoryCategory(str, Enum):
    DECISION = "decision"
    DISCOVERY = "discovery"
    GOTCHA = "gotcha"
    ARCHITECTURE = "architecture"
    SECURITY = "security"
    OPERATIONAL = "operational"
    INCIDENT = "incident"
    HANDOFF = "handoff"


class ForgeStatus(str, Enum):
    RAW = "raw"
    SMELTING = "smelting"
    REFINED = "refined"
    GATED = "gated"
    FORGED = "forged"
    REJECTED = "rejected"


class MaturityLevel(int, Enum):
    SESSION_VISIBLE = 1
    STANDARDIZED_FLOW = 2
    SECURE_FACTORY = 3
    HIERARCHICAL_COORD = 4
    AGENT_AUGMENTED = 5


def _now():
    return datetime.now(timezone.utc).isoformat()


def _new_id():
    return uuid.uuid4().hex[:8]


@dataclass
class WorkOrder:
    id: str = field(default_factory=_new_id)
    title: str = ""
    description: str = ""
    status: str = "backlog"
    stage: str = "plan"
    role: str = "line_worker"
    assigned_to: str = ""
    priority: int = 3
    acceptance_criteria: list = field(default_factory=list)
    dependencies: list = field(default_factory=list)
    security_considerations: str = ""
    evidence: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    activity_log: list = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def add_activity(self, action: str, details: str = "", actor: str = "system"):
        entry = {
            "id": _new_id(),
            "action": action,
            "details": details,
            "actor": actor,
            "timestamp": _now(),
        }
        self.activity_log.append(entry)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ForgeItem:
    id: str = field(default_factory=_new_id)
    raw_input: str = ""
    source: str = "manual"
    status: str = "raw"
    extracted_title: str = ""
    extracted_description: str = ""
    extracted_type: str = "unknown"
    suggested_priority: int = 3
    suggested_role: str = "line_worker"
    suggested_stage: str = "plan"
    suggested_tags: list = field(default_factory=list)
    suggested_product_line: str = ""
    suggested_project: str = ""
    confidence_score: int = 0
    gate_results: list = field(default_factory=list)
    gate_score: int = 0
    related_existing: list = field(default_factory=list)
    extraction_notes: list = field(default_factory=list)
    work_order_id: str = ""
    rejection_reason: str = ""
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def add_note(self, note: str):
        self.extraction_notes.append({
            "note": note,
            "timestamp": _now(),
        })

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class MemoryEntry:
    id: str = field(default_factory=_new_id)
    category: str = "discovery"
    content: str = ""
    source: str = ""
    tags: list = field(default_factory=list)
    created_at: str = field(default_factory=_now)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class QualityGate:
    id: str = field(default_factory=_new_id)
    name: str = ""
    stage: str = "code"
    gate_type: str = "manual"
    description: str = ""
    status: str = "not_run"
    last_run: str = ""
    evidence: str = ""
    command: str = ""
    last_output: str = ""
    last_exit_code: Optional[int] = None
    run_count: int = 0
    execution_history: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Session:
    id: str = field(default_factory=_new_id)
    started_at: str = field(default_factory=_now)
    ended_at: str = ""
    worker: str = ""
    role: str = "line_worker"
    tasks_worked: list = field(default_factory=list)
    notes: str = ""
    baton_pass: dict = field(default_factory=lambda: {
        "completed": [],
        "changed": [],
        "blocked": [],
        "next_actions": [],
        "decisions": []
    })
    active: bool = True

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class FactoryConfig:
    name: str = "SIRM Factory"
    description: str = ""
    maturity_level: int = 1
    policies: list = field(default_factory=list)
    roles_configured: list = field(default_factory=list)
    created_at: str = field(default_factory=_now)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
