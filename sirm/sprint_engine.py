from datetime import datetime, timezone, timedelta
from sirm.store import SIRMStore


PRIORITY_COLORS = {
    1: {"label": "CRITICAL", "color": "#f85149", "bg": "rgba(248,81,73,0.12)", "border": "rgba(248,81,73,0.4)"},
    2: {"label": "HIGH", "color": "#f0883e", "bg": "rgba(240,136,62,0.12)", "border": "rgba(240,136,62,0.4)"},
    3: {"label": "MEDIUM", "color": "#d29922", "bg": "rgba(210,153,34,0.12)", "border": "rgba(210,153,34,0.4)"},
    4: {"label": "LOW", "color": "#3fb950", "bg": "rgba(63,185,80,0.12)", "border": "rgba(63,185,80,0.4)"},
    5: {"label": "BACKLOG", "color": "#8b949e", "bg": "rgba(139,148,158,0.12)", "border": "rgba(139,148,158,0.4)"},
}

STATUS_STYLES = {
    "in_progress": {"icon": "⚡", "color": "#d29922", "label": "In Progress"},
    "ready": {"icon": "🎯", "color": "#58a6ff", "label": "Ready"},
    "blocked": {"icon": "🚫", "color": "#f85149", "label": "Blocked"},
    "verification": {"icon": "🔍", "color": "#bc8cff", "label": "Verification"},
    "done": {"icon": "✅", "color": "#3fb950", "label": "Done"},
    "backlog": {"icon": "📋", "color": "#8b949e", "label": "Backlog"},
}

STAGE_COLORS = {
    "plan": "#58a6ff",
    "code": "#bc8cff",
    "build": "#f0883e",
    "integrate": "#d29922",
    "release": "#3fb950",
    "operate": "#f778ba",
}


def _parse_dt(iso_str):
    try:
        if iso_str:
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
    except (ValueError, AttributeError):
        pass
    return None


def _time_ago(iso_str):
    dt = _parse_dt(iso_str)
    if not dt:
        return "unknown"
    now = datetime.now(timezone.utc)
    delta = now - dt
    if delta.days > 0:
        return f"{delta.days}d ago"
    hours = delta.seconds // 3600
    if hours > 0:
        return f"{hours}h ago"
    mins = delta.seconds // 60
    return f"{mins}m ago" if mins > 0 else "just now"


def generate_auto_prompts(store: SIRMStore) -> list:
    tasks = store.list_tasks()
    gates = store.list_gates()
    prompts = []

    blocked = [t for t in tasks if t.status == "blocked"]
    for t in blocked:
        prompts.append({
            "priority": 1,
            "type": "blocker",
            "icon": "🚫",
            "title": f"BLOCKED: {t.title}",
            "detail": t.description[:120] if t.description else "No details — needs triage",
            "action_label": "Unblock",
            "action_url": f"/tasks/{t.id}",
            "task_id": t.id,
        })

    verification = [t for t in tasks if t.status == "verification"]
    for t in verification:
        prompts.append({
            "priority": 2,
            "type": "verify",
            "icon": "🔍",
            "title": f"Verify: {t.title}",
            "detail": f"Stage: {t.stage} — needs sign-off",
            "action_label": "Review",
            "action_url": f"/tasks/{t.id}",
            "task_id": t.id,
        })

    failing_gates = [g for g in gates if g.status == "failing"]
    for g in failing_gates:
        prompts.append({
            "priority": 2,
            "type": "gate_fail",
            "icon": "🚨",
            "title": f"Gate Failing: {g.name}",
            "detail": f"Stage: {g.stage} — blocking pipeline progression",
            "action_label": "Fix",
            "action_url": f"/gates/{g.id}",
        })

    in_progress = [t for t in tasks if t.status == "in_progress"]
    stale_threshold = datetime.now(timezone.utc) - timedelta(days=3)
    for t in in_progress:
        updated = _parse_dt(t.updated_at)
        if updated and updated < stale_threshold:
            prompts.append({
                "priority": 2,
                "type": "stale",
                "icon": "⏰",
                "title": f"Stale WIP: {t.title}",
                "detail": f"No update in {_time_ago(t.updated_at)} — needs attention or re-scope",
                "action_label": "Check",
                "action_url": f"/tasks/{t.id}",
                "task_id": t.id,
            })

    ready = sorted([t for t in tasks if t.status == "ready"], key=lambda t: t.priority)
    for t in ready[:5]:
        prompts.append({
            "priority": t.priority,
            "type": "next_up",
            "icon": "🎯",
            "title": f"Ready: {t.title}",
            "detail": f"P{t.priority} · {t.stage} stage" + (f" · {t.assigned_to}" if t.assigned_to else ""),
            "action_label": "Start",
            "action_url": f"/tasks/{t.id}",
            "task_id": t.id,
        })

    not_run_gates = [g for g in gates if g.status == "not_run"]
    if not_run_gates:
        prompts.append({
            "priority": 3,
            "type": "gates_pending",
            "icon": "🏁",
            "title": f"{len(not_run_gates)} quality gates haven't been run",
            "detail": "Run gates to validate pipeline health",
            "action_label": "Run All",
            "action_url": "/gates",
        })

    if not in_progress and not blocked and not verification and ready:
        prompts.insert(0, {
            "priority": 1,
            "type": "idle",
            "icon": "⚡",
            "title": "No active work — pick up a ready item",
            "detail": f"{len(ready)} items waiting. Highest priority: {ready[0].title}",
            "action_label": "Go",
            "action_url": f"/tasks/{ready[0].id}",
            "task_id": ready[0].id,
        })

    if not tasks:
        prompts.append({
            "priority": 1,
            "type": "empty",
            "icon": "🏗️",
            "title": "No work orders yet",
            "detail": "Create your first work order or use the Foundry to intake raw ideas",
            "action_label": "Create",
            "action_url": "/tasks/new",
        })

    CATEGORY_ORDER = {"blocker": 0, "idle": 0, "empty": 0, "gate_fail": 1, "verify": 2, "stale": 3, "next_up": 4, "gates_pending": 5}
    prompts.sort(key=lambda p: (CATEGORY_ORDER.get(p["type"], 9), p["priority"]))
    return prompts


def get_sprint_briefing(store: SIRMStore) -> dict:
    state = store.get_radiator_state()
    tasks = store.list_tasks()
    auto_prompts = generate_auto_prompts(store)

    done_recent = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    for t in tasks:
        if t.status == "done":
            updated = _parse_dt(t.updated_at)
            if updated and updated > cutoff:
                done_recent.append({
                    **t.to_dict(),
                    "time_ago": _time_ago(t.updated_at),
                    "priority_style": PRIORITY_COLORS.get(t.priority, PRIORITY_COLORS[3]),
                })

    wip_enriched = []
    for t in tasks:
        if t.status == "in_progress":
            wip_enriched.append({
                **t.to_dict(),
                "time_ago": _time_ago(t.updated_at),
                "priority_style": PRIORITY_COLORS.get(t.priority, PRIORITY_COLORS[3]),
                "stage_color": STAGE_COLORS.get(t.stage, "#8b949e"),
            })

    ready_enriched = []
    for t in sorted([t for t in tasks if t.status == "ready"], key=lambda t: t.priority):
        ready_enriched.append({
            **t.to_dict(),
            "priority_style": PRIORITY_COLORS.get(t.priority, PRIORITY_COLORS[3]),
            "stage_color": STAGE_COLORS.get(t.stage, "#8b949e"),
        })

    blocked_enriched = []
    for t in tasks:
        if t.status == "blocked":
            blocked_enriched.append({
                **t.to_dict(),
                "time_ago": _time_ago(t.updated_at),
                "priority_style": PRIORITY_COLORS.get(t.priority, PRIORITY_COLORS[3]),
            })

    velocity = len(done_recent)
    active_count = len(wip_enriched)
    ready_count = len(ready_enriched)
    blocked_count = len(blocked_enriched)

    if blocked_count > 0:
        momentum = "BLOCKED"
        momentum_color = "#f85149"
    elif active_count == 0 and ready_count > 0:
        momentum = "IDLE"
        momentum_color = "#d29922"
    elif active_count > 0:
        momentum = "MOVING"
        momentum_color = "#3fb950"
    else:
        momentum = "EMPTY"
        momentum_color = "#8b949e"

    baton = state.get("last_baton_pass")
    baton_next = baton.get("next_actions", []) if baton else []
    baton_completed = baton.get("completed", []) if baton else []
    baton_blocked = baton.get("blocked", []) if baton else []

    return {
        **state,
        "auto_prompts": auto_prompts,
        "done_recent": done_recent,
        "wip_enriched": wip_enriched,
        "ready_enriched": ready_enriched,
        "blocked_enriched": blocked_enriched,
        "velocity_7d": velocity,
        "momentum": momentum,
        "momentum_color": momentum_color,
        "priority_colors": PRIORITY_COLORS,
        "status_styles": STATUS_STYLES,
        "stage_colors": STAGE_COLORS,
        "baton_next": baton_next,
        "baton_completed": baton_completed,
        "baton_blocked": baton_blocked,
    }
