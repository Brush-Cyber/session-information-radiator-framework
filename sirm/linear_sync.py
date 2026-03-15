import json
from pathlib import Path
from sirm.store import SIRMStore
from sirm.models import _now
from sirm import linear_client

SYNC_MAP_PATH = Path(".sirm/linear_sync.json")

SIRM_TO_LINEAR_STATUS = {
    "backlog": "Backlog",
    "ready": "Todo",
    "in_progress": "In Progress",
    "verification": "In Review",
    "done": "Done",
    "blocked": "Backlog",
}

SIRM_TO_LINEAR_PRIORITY = {
    1: 1,
    2: 2,
    3: 3,
    4: 4,
    5: 0,
}

LINEAR_TO_SIRM_STATUS = {
    "backlog": "backlog",
    "triage": "backlog",
    "todo": "ready",
    "in progress": "in_progress",
    "in review": "verification",
    "done": "done",
    "canceled": "done",
    "cancelled": "done",
    "duplicate": "done",
}

LINEAR_TO_SIRM_PRIORITY = {
    0: 5,
    1: 1,
    2: 2,
    3: 3,
    4: 4,
}

SIRM_ROLE_TO_LABEL = {
    "line_worker": "role/line-worker",
    "line_manager": "role/line-manager",
    "assembly_manager": "role/assembly-manager",
    "factory_manager": "role/factory-manager",
    "quality_overlay": "role/line-manager",
    "plant_governance": "role/plant-governance",
}

TARGET_TEAM_KEY = "BRU"

SIRM_STAGE_TO_LABEL = {
    "plan": "sirm/governance",
    "code": "sirm/execution",
    "build": "sirm/artifact-runtime",
    "integrate": "sirm/orchestration",
    "release": "sirm/verification",
    "operate": "sirm/radiator",
}


def _load_sync_map():
    if SYNC_MAP_PATH.exists():
        with open(SYNC_MAP_PATH) as f:
            return json.load(f)
    return {"task_to_issue": {}, "issue_to_task": {}, "team_id": None}


def _save_sync_map(sync_map):
    SYNC_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SYNC_MAP_PATH, "w") as f:
        json.dump(sync_map, f, indent=2)


def _find_state_id(states, target_name):
    for state in states:
        if state["name"].lower() == target_name.lower():
            return state["id"]
    return None


def _find_label_ids(labels, target_names):
    result = []
    for label in labels:
        if label["name"] in target_names:
            result.append(label["id"])
    return result


def _build_description(task):
    parts = []
    if task.description:
        parts.append(task.description)

    if task.acceptance_criteria:
        parts.append("\n**Acceptance Criteria:**")
        for c in task.acceptance_criteria:
            parts.append(f"- [ ] {c}")

    if task.security_considerations:
        parts.append(f"\n**Security Considerations:**\n{task.security_considerations}")

    if task.dependencies:
        parts.append(f"\n**Dependencies:** {', '.join(task.dependencies)}")

    if task.evidence:
        parts.append("\n**Evidence:**")
        for e in task.evidence:
            parts.append(f"- {e.get('content', '')} ({e.get('added_at', '')[:16]})")

    parts.append(f"\n---\n*SIRM Task ID: {task.id} | Stage: {task.stage} | Role: {task.role}*")
    return "\n".join(parts)


def sync_to_linear(store: SIRMStore):
    sync_map = _load_sync_map()
    teams = linear_client.get_teams()
    if not teams:
        raise RuntimeError("No Linear teams found")

    team = next((t for t in teams if t["key"] == TARGET_TEAM_KEY), None)
    if not team:
        raise RuntimeError(f"Linear team '{TARGET_TEAM_KEY}' not found")
    team_id = team["id"]
    sync_map["team_id"] = team_id

    states = linear_client.get_team_states(team_id)
    labels = linear_client.get_team_labels(team_id)
    tasks = store.list_tasks()

    results = {"created": [], "updated": [], "errors": []}

    for task in tasks:
        try:
            target_state_name = SIRM_TO_LINEAR_STATUS.get(task.status, "Backlog")
            state_id = _find_state_id(states, target_state_name)

            linear_priority = SIRM_TO_LINEAR_PRIORITY.get(task.priority, 3)

            target_label_names = []
            role_label = SIRM_ROLE_TO_LABEL.get(task.role)
            if role_label:
                target_label_names.append(role_label)
            stage_label = SIRM_STAGE_TO_LABEL.get(task.stage)
            if stage_label:
                target_label_names.append(stage_label)
            label_ids = _find_label_ids(labels, target_label_names)

            description = _build_description(task)

            existing_issue_id = sync_map["task_to_issue"].get(task.id)

            if existing_issue_id:
                issue = linear_client.update_issue(
                    existing_issue_id,
                    state_id=state_id,
                    title=task.title,
                    description=description,
                    priority=linear_priority,
                    label_ids=label_ids if label_ids else None,
                )
                if issue:
                    results["updated"].append({
                        "task_id": task.id,
                        "issue_id": issue["identifier"],
                        "title": task.title,
                        "url": issue.get("url", ""),
                    })
            else:
                issue = linear_client.create_issue(
                    team_id=team_id,
                    title=task.title,
                    description=description,
                    state_id=state_id,
                    priority=linear_priority,
                    label_ids=label_ids if label_ids else None,
                )
                sync_map["task_to_issue"][task.id] = issue["id"]
                sync_map["issue_to_task"][issue["id"]] = task.id
                results["created"].append({
                    "task_id": task.id,
                    "issue_id": issue["identifier"],
                    "title": task.title,
                    "url": issue.get("url", ""),
                })

        except Exception as e:
            results["errors"].append({
                "task_id": task.id,
                "title": task.title,
                "error": str(e),
            })

    _save_sync_map(sync_map)
    return results


def pull_from_linear(store: SIRMStore):
    sync_map = _load_sync_map()
    task_to_issue = sync_map.get("task_to_issue", {})

    if not task_to_issue:
        return {"updated": [], "errors": [], "unchanged": []}

    results = {"updated": [], "errors": [], "unchanged": []}

    for task_id, issue_id in task_to_issue.items():
        try:
            issue = linear_client.get_issue(issue_id)
            if not issue:
                results["errors"].append({
                    "task_id": task_id,
                    "error": "Issue not found in Linear",
                })
                continue

            task = store.get_task(task_id)
            if not task:
                results["errors"].append({
                    "task_id": task_id,
                    "error": "Task not found in SIRM",
                })
                continue

            linear_state_name = issue.get("state", {}).get("name", "").lower()
            new_sirm_status = LINEAR_TO_SIRM_STATUS.get(linear_state_name)

            changed = False

            if new_sirm_status and new_sirm_status != task.status:
                old_status = task.status

                advancement = new_sirm_status in ("verification", "done")
                gate_blocked = False
                if advancement:
                    gate_check = store.check_stage_gates(task.stage)
                    if not gate_check["passed"]:
                        gate_blocked = True
                        failing = [g.name for g in gate_check.get("failing", [])]
                        not_run = [g.name for g in gate_check.get("not_run", [])]
                        results["errors"].append({
                            "task_id": task.id,
                            "title": task.title,
                            "error": f"Gates blocking advancement to {new_sirm_status}: failing={failing}, not_run={not_run}",
                        })

                if not gate_blocked:
                    task.status = new_sirm_status
                    if hasattr(task, "add_activity"):
                        task.add_activity(
                            "status_change",
                            f"Status changed from '{old_status}' to '{new_sirm_status}' (synced from Linear)",
                            actor="linear_sync",
                        )
                    changed = True

            if changed:
                store.save_task(task)
                results["updated"].append({
                    "task_id": task.id,
                    "title": task.title,
                    "old_status": old_status,
                    "new_status": new_sirm_status,
                    "linear_state": issue.get("state", {}).get("name", ""),
                })
            else:
                results["unchanged"].append({
                    "task_id": task.id,
                    "title": task.title,
                })

        except Exception as e:
            results["errors"].append({
                "task_id": task_id,
                "error": str(e),
            })

    sync_map["last_pull_at"] = _now()
    _save_sync_map(sync_map)
    return results


def get_sync_status(store: SIRMStore):
    sync_map = _load_sync_map()
    tasks = store.list_tasks()
    synced = []
    unsynced = []
    for task in tasks:
        if task.id in sync_map.get("task_to_issue", {}):
            synced.append(task)
        else:
            unsynced.append(task)
    return {
        "synced_count": len(synced),
        "unsynced_count": len(unsynced),
        "total": len(tasks),
        "team_id": sync_map.get("team_id"),
        "sync_map": sync_map,
        "last_pull_at": sync_map.get("last_pull_at"),
    }
