from sirm.store import SIRMStore
from sirm.sprint_engine import generate_auto_prompts


def format_radiator_text(store: SIRMStore) -> str:
    state = store.get_radiator_state()
    lines = []
    factory = state["factory"]

    lines.append(f"{'=' * 60}")
    lines.append(f"  SPRINT COMMAND CENTER — {factory['name']}")
    lines.append(f"  Maturity Level: {factory['maturity_level']} | "
                 f"Total Tasks: {state['total_tasks']}")
    lines.append(f"{'=' * 60}")

    session = state.get("active_session")
    if session:
        lines.append(f"  Active Session: {session['id']} | "
                     f"Worker: {session.get('worker', 'unassigned')} | "
                     f"Role: {session.get('role', 'line_worker')}")
    else:
        lines.append("  No active session")

    lines.append(f"{'─' * 60}")

    tc = state["task_counts"]
    lines.append("  WORK STATE")
    lines.append(f"    Backlog: {tc['backlog']}  |  Ready: {tc['ready']}  |  "
                 f"In Progress: {tc['in_progress']}  |  Verification: {tc['verification']}")
    lines.append(f"    Done: {tc['done']}  |  Blocked: {tc['blocked']}")

    if state["wip_tasks"]:
        lines.append(f"{'─' * 60}")
        lines.append("  CURRENT WORK (In Progress)")
        for t in state["wip_tasks"]:
            lines.append(f"    [{t['id']}] {t['title']} ({t['stage']}) → {t.get('assigned_to', 'unassigned')}")

    if state["blocked_tasks"]:
        lines.append(f"{'─' * 60}")
        lines.append("  ⛔ BLOCKED")
        for t in state["blocked_tasks"]:
            lines.append(f"    [{t['id']}] {t['title']}")

    if state["ready_tasks"]:
        lines.append(f"{'─' * 60}")
        lines.append("  READY (Next Up)")
        for t in state["ready_tasks"][:3]:
            lines.append(f"    [{t['id']}] {t['title']} (P{t['priority']})")

    gs = state["gate_summary"]
    lines.append(f"{'─' * 60}")
    lines.append("  QUALITY GATES")
    lines.append(f"    Passing: {gs['passing']}  |  Failing: {gs['failing']}  |  "
                 f"Not Run: {gs['not_run']}  |  Skipped: {gs['skipped']}")

    failing_gates = [g for g in state["gates"] if g["status"] == "failing"]
    if failing_gates:
        for g in failing_gates:
            lines.append(f"    FAIL: {g['name']} ({g['stage']})")

    if state["recent_memories"]:
        lines.append(f"{'─' * 60}")
        lines.append("  RECENT MEMORY")
        for m in state["recent_memories"][:3]:
            content_preview = m["content"][:80] + "..." if len(m["content"]) > 80 else m["content"]
            lines.append(f"    [{m['category']}] {content_preview}")

    baton = state.get("last_baton_pass")
    if baton:
        lines.append(f"{'─' * 60}")
        lines.append("  LAST BATON PASS")
        if baton.get("next_actions"):
            lines.append("    Next Actions:")
            for a in baton["next_actions"][:3]:
                lines.append(f"      → {a}")
        if baton.get("blocked"):
            lines.append("    Blocked:")
            for b in baton["blocked"][:3]:
                lines.append(f"      ⛔ {b}")

    prompts = generate_auto_prompts(store)
    if prompts:
        lines.append(f"{'─' * 60}")
        lines.append("  ⚡ WHAT'S NEXT (auto-generated)")
        for p in prompts[:5]:
            prio = p.get("priority", 3)
            label = {1: "CRITICAL", 2: "HIGH", 3: "MEDIUM", 4: "LOW", 5: "BACKLOG"}.get(prio, "")
            lines.append(f"    {p['icon']} [{label}] {p['title']}")
            if p.get("detail"):
                lines.append(f"       {p['detail'][:100]}")

    lines.append(f"{'=' * 60}")
    return "\n".join(lines)
