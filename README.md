# SIRM — Secure Intelligent Release Management

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
