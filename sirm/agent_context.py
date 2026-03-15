from sirm.store import SIRMStore


ROLE_DESCRIPTIONS = {
    "plant_governance": "Policy, architecture boundaries, release classes, risk decisions. Human accountability required.",
    "factory_manager": "End-to-end throughput, risk, cost, and abnormality detection. Human release authority.",
    "assembly_manager": "Integrate outputs across cells, verify contracts. Synthesis and impact analysis.",
    "line_manager": "Decompose work, maintain local flow. Decomposition, triage, summarization.",
    "line_worker": "Execute bounded task and return evidence. Scope, tools, and gates must be clear.",
    "quality_overlay": "Keep the factory safe, observable, and easy to use. Detection and routine enforcement.",
}

STATUS_ORDER = ["backlog", "ready", "in_progress", "verification", "done", "blocked"]
STAGE_ORDER = ["plan", "code", "build", "integrate", "release", "operate"]


def generate_agents_md(store: SIRMStore) -> str:
    config = store.get_config()
    tasks = store.list_tasks()
    gates = store.list_gates()
    memories = store.list_memories()
    active_session = store.get_active_session()
    sessions = store.list_sessions()

    lines = []

    lines.append("# AGENTS.md")
    lines.append("")
    lines.append(f"Factory: **{config.name}**")
    if config.description:
        lines.append(f"Description: {config.description}")
    lines.append(f"Maturity Level: {config.maturity_level}")
    lines.append(f"Generated from SIRM factory state.")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Role Hierarchy")
    lines.append("")
    for role, desc in ROLE_DESCRIPTIONS.items():
        lines.append(f"- **{role}**: {desc}")
    lines.append("")

    if config.policies:
        lines.append("## Policies")
        lines.append("")
        for policy in config.policies:
            lines.append(f"- {policy}")
        lines.append("")

    active_tasks = [t for t in tasks if t.status not in ("done",)]
    if active_tasks:
        lines.append("---")
        lines.append("")
        lines.append("## Active Work Orders")
        lines.append("")
        for task in sorted(active_tasks, key=lambda t: (t.priority, STATUS_ORDER.index(t.status) if t.status in STATUS_ORDER else 99)):
            lines.append(f"### [{task.id}] {task.title}")
            lines.append(f"- **Status**: {task.status}")
            lines.append(f"- **Stage**: {task.stage}")
            lines.append(f"- **Role**: {task.role}")
            lines.append(f"- **Priority**: {task.priority}")
            if task.assigned_to:
                lines.append(f"- **Assigned To**: {task.assigned_to}")
            if task.description:
                lines.append(f"- **Description**: {task.description}")
            if task.acceptance_criteria:
                lines.append("- **Acceptance Criteria**:")
                for ac in task.acceptance_criteria:
                    lines.append(f"  - [ ] {ac}")
            if task.dependencies:
                lines.append(f"- **Dependencies**: {', '.join(task.dependencies)}")
            if task.security_considerations:
                lines.append(f"- **Security**: {task.security_considerations}")
            if task.tags:
                lines.append(f"- **Tags**: {', '.join(task.tags)}")
            lines.append("")
    else:
        lines.append("## Active Work Orders")
        lines.append("")
        lines.append("No active work orders.")
        lines.append("")

    if gates:
        lines.append("---")
        lines.append("")
        lines.append("## Quality Gate Requirements")
        lines.append("")
        for stage in STAGE_ORDER:
            stage_gates = [g for g in gates if g.stage == stage]
            if stage_gates:
                lines.append(f"### Stage: {stage}")
                for gate in stage_gates:
                    status_icon = {"passing": "PASS", "failing": "FAIL", "not_run": "NOT RUN", "skipped": "SKIP"}.get(gate.status, gate.status)
                    lines.append(f"- **{gate.name}** [{status_icon}] ({gate.gate_type}): {gate.description}")
                    if gate.command:
                        lines.append(f"  - Command: `{gate.command}`")
                lines.append("")

    if memories:
        lines.append("---")
        lines.append("")
        lines.append("## Relevant Memory")
        lines.append("")
        for entry in memories:
            lines.append(f"- **[{entry.category}]** {entry.content}")
            if entry.source:
                lines.append(f"  - Source: {entry.source}")
            if entry.tags:
                lines.append(f"  - Tags: {', '.join(entry.tags)}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Session Context")
    lines.append("")
    if active_session:
        lines.append(f"- **Active Session**: {active_session.id}")
        lines.append(f"- **Started**: {active_session.started_at}")
        if active_session.worker:
            lines.append(f"- **Worker**: {active_session.worker}")
        lines.append(f"- **Role**: {active_session.role}")
        if active_session.tasks_worked:
            lines.append(f"- **Tasks Worked**: {', '.join(active_session.tasks_worked)}")
        if active_session.notes:
            lines.append(f"- **Notes**: {active_session.notes}")
    else:
        lines.append("No active session.")
    lines.append("")

    last_baton = None
    for s in sessions:
        if not s.active and s.baton_pass:
            has_content = any(s.baton_pass.get(k) for k in ["completed", "changed", "blocked", "next_actions", "decisions"])
            if has_content:
                last_baton = s.baton_pass
                break

    if last_baton:
        lines.append("### Last Baton Pass")
        lines.append("")
        for key in ["completed", "changed", "blocked", "next_actions", "decisions"]:
            items = last_baton.get(key, [])
            if items:
                lines.append(f"**{key.replace('_', ' ').title()}**:")
                for item in items:
                    lines.append(f"- {item}")
                lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    total = len(tasks)
    done_count = len([t for t in tasks if t.status == "done"])
    active_count = len(active_tasks)
    blocked_count = len([t for t in tasks if t.status == "blocked"])
    passing_gates = len([g for g in gates if g.status == "passing"])
    failing_gates = len([g for g in gates if g.status == "failing"])
    total_gates = len(gates)

    lines.append(f"- Total work orders: {total} ({done_count} done, {active_count} active, {blocked_count} blocked)")
    lines.append(f"- Quality gates: {passing_gates}/{total_gates} passing, {failing_gates} failing")
    lines.append(f"- Memory entries: {len(memories)}")
    lines.append(f"- Total sessions: {len(sessions)}")
    lines.append("")

    return "\n".join(lines)
