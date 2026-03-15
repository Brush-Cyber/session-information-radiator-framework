import subprocess
import os
import re
import shlex
import logging
from sirm.models import MemoryEntry, _now, _new_id
from sirm.agent_context import generate_agents_md

logger = logging.getLogger(__name__)

STAGE_ORDER = ["plan", "code", "build", "integrate", "release", "operate"]

COMMAND_ALLOWLIST = [
    "pytest", "python", "npm", "npx", "node", "make", "cargo",
    "go", "ruff", "flake8", "pylint", "mypy", "black", "isort",
    "eslint", "prettier", "tsc", "jest", "mocha", "trivy",
    "bandit", "safety", "pip", "uv", "grep", "find", "cat",
    "echo", "test", "true", "false",
]

GATE_EXECUTION_TIMEOUT = 30


DANGEROUS_PATTERNS = ['`', '$(', '${', '<(', '>(', ';', '\n', '\r']


def _has_unquoted_shell_operator(command):
    in_single = False
    in_double = False
    escaped = False
    i = 0
    while i < len(command):
        c = command[i]
        if escaped:
            escaped = False
            i += 1
            continue
        if c == '\\':
            escaped = True
            i += 1
            continue
        if c == "'" and not in_double:
            in_single = not in_single
        elif c == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if c == '|':
                if i + 1 < len(command) and command[i + 1] == '|':
                    i += 2
                    continue
                return True
            if c == '&':
                if i + 1 < len(command) and command[i + 1] == '&':
                    i += 2
                    continue
                return True
            if c in ('<', '>'):
                return True
        i += 1
    return False


def _is_command_allowed(command):
    if not command or not command.strip():
        return False
    for pattern in DANGEROUS_PATTERNS:
        if pattern in command:
            return False
    if _has_unquoted_shell_operator(command):
        return False
    segments = re.split(r'\s*(?:&&|\|\|)\s*', command)
    for segment in segments:
        segment = segment.strip()
        if not segment:
            return False
        try:
            parts = shlex.split(segment)
        except ValueError:
            return False
        if not parts:
            return False
        base_cmd = os.path.basename(parts[0])
        if base_cmd not in COMMAND_ALLOWLIST:
            return False
    return True


def next_stage(current_stage):
    try:
        idx = STAGE_ORDER.index(current_stage)
    except ValueError:
        return None
    if idx >= len(STAGE_ORDER) - 1:
        return None
    return STAGE_ORDER[idx + 1]


def run_gate(gate):
    if not gate.command or not _is_command_allowed(gate.command):
        return None

    try:
        result = subprocess.run(
            gate.command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=GATE_EXECUTION_TIMEOUT,
            cwd=os.getcwd(),
        )
        exit_code = result.returncode
        output = result.stdout
        if result.stderr:
            output += "\n--- STDERR ---\n" + result.stderr
        output = output[:50000]
    except subprocess.TimeoutExpired:
        exit_code = -1
        output = f"Command timed out after {GATE_EXECUTION_TIMEOUT} seconds"
    except Exception as e:
        exit_code = -1
        output = f"Execution error: {str(e)}"

    gate.status = "passing" if exit_code == 0 else "failing"
    gate.last_run = _now()
    gate.last_output = output
    gate.last_exit_code = exit_code
    gate.run_count = (gate.run_count or 0) + 1
    gate.evidence = f"Exit code: {exit_code} | Auto-run at {gate.last_run}"

    history_entry = {
        "id": _new_id(),
        "timestamp": gate.last_run,
        "exit_code": exit_code,
        "status": gate.status,
        "output": output[:10000],
    }
    if not isinstance(getattr(gate, 'execution_history', None), list):
        gate.execution_history = []
    gate.execution_history.append(history_entry)
    if len(gate.execution_history) > 50:
        gate.execution_history = gate.execution_history[-50:]

    return {
        "gate_id": gate.id,
        "name": gate.name,
        "status": gate.status,
        "exit_code": exit_code,
    }


def run_all_automated_gates(store):
    all_gates = store.list_gates()
    results = {"passed": 0, "failed": 0, "skipped": 0, "details": []}

    for gate in all_gates:
        if gate.gate_type != "automated" or not gate.command:
            results["skipped"] += 1
            results["details"].append({
                "gate_id": gate.id,
                "name": gate.name,
                "stage": gate.stage,
                "status": "skipped",
                "reason": "manual gate or no command",
            })
            continue

        if not _is_command_allowed(gate.command):
            results["skipped"] += 1
            results["details"].append({
                "gate_id": gate.id,
                "name": gate.name,
                "stage": gate.stage,
                "status": "skipped",
                "reason": "command not in allowlist",
            })
            continue

        gate_result = run_gate(gate)
        store.save_gate(gate)

        if gate_result and gate_result["status"] == "passing":
            results["passed"] += 1
        else:
            results["failed"] += 1

        results["details"].append({
            "gate_id": gate.id,
            "name": gate.name,
            "stage": gate.stage,
            "status": gate_result["status"] if gate_result else "error",
            "exit_code": gate_result["exit_code"] if gate_result else -1,
        })

    return results


def auto_advance_tasks(store):
    tasks = store.list_tasks(status="in_progress")
    advanced = []
    blocked = []
    already_final = []

    for task in tasks:
        nxt = next_stage(task.stage)
        if nxt is None:
            already_final.append({
                "task_id": task.id,
                "title": task.title,
                "stage": task.stage,
                "reason": "already at final stage",
            })
            continue

        gate_check = store.check_stage_gates(task.stage)

        if not gate_check["passed"]:
            failing_names = [g.name for g in gate_check["failing"]]
            not_run_names = [g.name for g in gate_check["not_run"]]
            blocked.append({
                "task_id": task.id,
                "title": task.title,
                "stage": task.stage,
                "failing": failing_names,
                "not_run": not_run_names,
            })
            continue

        old_stage = task.stage
        task.stage = nxt
        task.add_activity(
            "auto_advanced",
            f"Auto-advanced from '{old_stage}' to '{nxt}' by pipeline engine",
            actor="pipeline"
        )
        store.save_task(task)
        advanced.append({
            "task_id": task.id,
            "title": task.title,
            "from_stage": old_stage,
            "to_stage": nxt,
        })

    return {
        "advanced": advanced,
        "blocked": blocked,
        "already_final": already_final,
        "total_processed": len(tasks),
    }


def run_pipeline(store):
    gate_results = run_all_automated_gates(store)
    advance_results = auto_advance_tasks(store)

    return {
        "gates": gate_results,
        "advancement": advance_results,
        "summary": {
            "gates_passed": gate_results["passed"],
            "gates_failed": gate_results["failed"],
            "gates_skipped": gate_results["skipped"],
            "tasks_advanced": len(advance_results["advanced"]),
            "tasks_blocked": len(advance_results["blocked"]),
            "tasks_final": len(advance_results["already_final"]),
        }
    }


def _pull_linear_safe(store):
    try:
        from sirm import linear_sync
        result = linear_sync.pull_from_linear(store)
        updated = len(result.get("updated", []))
        errors = len(result.get("errors", []))
        return {
            "success": True,
            "updated": updated,
            "errors": errors,
            "details": result,
        }
    except Exception as e:
        logger.warning(f"Linear pull skipped: {e}")
        return {
            "success": False,
            "error": str(e),
            "updated": 0,
            "errors": 0,
        }


def _generate_context_snapshot(store):
    try:
        content = generate_agents_md(store)
        return {
            "success": True,
            "length": len(content),
        }
    except Exception as e:
        logger.error(f"AGENTS.md generation failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


def _create_session_memory_snapshot(store, session_id):
    try:
        state = store.get_radiator_state()
        snapshot_parts = [
            f"Session {session_id} started at {_now()}",
            f"Factory health: {state.get('health_score', 'N/A')}%",
            f"Tasks: {state.get('total_tasks', 0)} total, {state['task_counts'].get('in_progress', 0)} in progress, {state['task_counts'].get('blocked', 0)} blocked",
            f"Gates: {state['gate_summary'].get('passing', 0)} passing, {state['gate_summary'].get('failing', 0)} failing, {state['gate_summary'].get('not_run', 0)} not run",
            f"Sessions: {state.get('session_count', 0)} total",
        ]
        snapshot_content = " | ".join(snapshot_parts)

        entry = MemoryEntry(
            category="operational",
            content=snapshot_content,
            source=f"session-bootstrap:{session_id}",
            tags=["session-start", "auto-bootstrap", session_id],
        )
        store.save_memory(entry)
        return {
            "success": True,
            "memory_id": entry.id,
            "content": snapshot_content,
        }
    except Exception as e:
        logger.error(f"Session memory snapshot failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


def bootstrap_session(store, session_id):
    results = {
        "session_id": session_id,
        "timestamp": _now(),
        "gates": None,
        "linear": None,
        "context": None,
        "memory_snapshot": None,
    }

    results["gates"] = run_all_automated_gates(store)
    results["linear"] = _pull_linear_safe(store)
    results["context"] = _generate_context_snapshot(store)
    results["memory_snapshot"] = _create_session_memory_snapshot(store, session_id)

    summary_parts = []
    g = results["gates"]
    summary_parts.append(f"Gates: {g['passed']} passed, {g['failed']} failed, {g['skipped']} skipped")

    lin = results["linear"]
    if lin["success"]:
        summary_parts.append(f"Linear: {lin['updated']} updated")
    else:
        summary_parts.append("Linear: skipped")

    c = results["context"]
    if c["success"]:
        summary_parts.append(f"AGENTS.md: generated ({c['length']} chars)")
    else:
        summary_parts.append("AGENTS.md: failed")

    m = results["memory_snapshot"]
    if m["success"]:
        summary_parts.append("Memory snapshot: created")
    else:
        summary_parts.append("Memory snapshot: failed")

    results["summary"] = " | ".join(summary_parts)

    return results
