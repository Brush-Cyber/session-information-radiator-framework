"""
Persistent Agent Memory — PostgreSQL-backed cross-session context.

Every agent session (any Repl, any chat) calls load_session_context() on startup.
This returns directives, current context, recent session history, and the SIRM
task queue state — everything needed to act autonomously without asking Douglas.

At session end, call close_session() to write the baton pass.
"""

import os
import json
import logging
from datetime import datetime, timezone
from contextlib import contextmanager
import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")


@contextmanager
def _conn():
    c = psycopg2.connect(DATABASE_URL)
    try:
        yield c
    finally:
        c.close()


def load_directives():
    with _conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT directive, priority, category FROM agent_directives "
            "WHERE active = TRUE ORDER BY priority, id"
        )
        return [dict(r) for r in cur.fetchall()]


def load_context():
    with _conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT context_key, context_value, category, updated_at "
            "FROM agent_context ORDER BY category, context_key"
        )
        return {r["context_key"]: dict(r) for r in cur.fetchall()}


def load_recent_sessions(limit=3):
    with _conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT session_id, repl_name, started_at, ended_at, summary, "
            "tasks_completed, tasks_started, decisions_made, escalations, next_actions "
            "FROM agent_sessions ORDER BY started_at DESC LIMIT %s",
            (limit,)
        )
        rows = []
        for r in cur.fetchall():
            row = dict(r)
            for field in ['tasks_completed', 'tasks_started', 'decisions_made', 'escalations', 'next_actions']:
                try:
                    row[field] = json.loads(row[field]) if row[field] else []
                except (json.JSONDecodeError, TypeError):
                    row[field] = []
            rows.append(row)
        return rows


def load_task_queue():
    with _conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT id, title, status, priority, stage, description "
            "FROM sirm_tasks "
            "WHERE status IN ('in_progress', 'ready', 'blocked', 'verification') "
            "ORDER BY priority, "
            "CASE status "
            "  WHEN 'blocked' THEN 0 "
            "  WHEN 'in_progress' THEN 1 "
            "  WHEN 'verification' THEN 2 "
            "  WHEN 'ready' THEN 3 "
            "  ELSE 4 END, "
            "updated_at DESC"
        )
        return [dict(r) for r in cur.fetchall()]


def load_recent_memories(limit=10):
    with _conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT id, category, content, source, created_at "
            "FROM sirm_memories ORDER BY created_at DESC LIMIT %s",
            (limit,)
        )
        return [dict(r) for r in cur.fetchall()]


def load_session_context():
    directives = load_directives()
    context = load_context()
    recent_sessions = load_recent_sessions(limit=3)
    task_queue = load_task_queue()
    recent_memories = load_recent_memories(limit=10)

    last_session = recent_sessions[0] if recent_sessions else None
    next_actions_from_last = last_session.get("next_actions", []) if last_session else []

    blocked = [t for t in task_queue if t["status"] == "blocked"]
    in_progress = [t for t in task_queue if t["status"] == "in_progress"]
    ready = [t for t in task_queue if t["status"] == "ready"]
    verification = [t for t in task_queue if t["status"] == "verification"]

    if blocked:
        top_action = f"UNBLOCK: {blocked[0]['title']} (P{blocked[0]['priority']})"
        top_task = blocked[0]
    elif in_progress:
        top_action = f"CONTINUE: {in_progress[0]['title']} (P{in_progress[0]['priority']})"
        top_task = in_progress[0]
    elif verification:
        top_action = f"VERIFY: {verification[0]['title']} (P{verification[0]['priority']})"
        top_task = verification[0]
    elif ready:
        top_action = f"START: {ready[0]['title']} (P{ready[0]['priority']})"
        top_task = ready[0]
    else:
        top_action = "NO QUEUED WORK — check backlog or Forge for new intake"
        top_task = None

    return {
        "directives": directives,
        "context": context,
        "recent_sessions": recent_sessions,
        "last_session_baton": {
            "summary": last_session.get("summary", "") if last_session else "",
            "next_actions": next_actions_from_last,
            "decisions": last_session.get("decisions_made", []) if last_session else [],
        },
        "task_queue": {
            "blocked": blocked,
            "in_progress": in_progress,
            "verification": verification,
            "ready": ready,
            "total_active": len(task_queue),
        },
        "recent_memories": recent_memories,
        "top_action": top_action,
        "top_task": top_task,
    }


def open_session(session_id, repl_name=""):
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO agent_sessions (session_id, repl_name, started_at) "
            "VALUES (%s, %s, NOW())",
            (session_id, repl_name)
        )
        conn.commit()
    logger.info(f"Agent session opened: {session_id} on {repl_name}")


def close_session(session_id, summary="", tasks_completed=None, tasks_started=None,
                  decisions_made=None, escalations=None, next_actions=None):
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE agent_sessions SET ended_at = NOW(), summary = %s, "
            "tasks_completed = %s, tasks_started = %s, decisions_made = %s, "
            "escalations = %s, next_actions = %s "
            "WHERE session_id = %s AND ended_at IS NULL",
            (
                summary,
                json.dumps(tasks_completed or []),
                json.dumps(tasks_started or []),
                json.dumps(decisions_made or []),
                json.dumps(escalations or []),
                json.dumps(next_actions or []),
                session_id,
            )
        )
        conn.commit()
    logger.info(f"Agent session closed: {session_id}")


def set_context(key, value, category="operational"):
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO agent_context (context_key, context_value, category) "
            "VALUES (%s, %s, %s) "
            "ON CONFLICT (context_key) DO UPDATE SET "
            "context_value = EXCLUDED.context_value, category = EXCLUDED.category, updated_at = NOW()",
            (key, value, category)
        )
        conn.commit()


def add_directive(directive, priority=2, category="general", source="system"):
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO agent_directives (directive, priority, category, source) "
            "VALUES (%s, %s, %s, %s)",
            (directive, priority, category, source)
        )
        conn.commit()


def add_memory(content, category="operational", source="agent", tags=None):
    from sirm.models import _new_id, _now
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO sirm_memories (id, category, content, source, tags, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (_new_id(), category, content, source, json.dumps(tags or []), _now())
        )
        conn.commit()


def format_briefing(ctx):
    lines = []
    lines.append("=" * 60)
    lines.append("AGENT SESSION BRIEFING")
    lines.append("=" * 60)

    lines.append("")
    lines.append(f">> TOP ACTION: {ctx['top_action']}")

    if ctx["last_session_baton"]["summary"]:
        lines.append("")
        lines.append("--- LAST SESSION ---")
        lines.append(ctx["last_session_baton"]["summary"])
        if ctx["last_session_baton"]["next_actions"]:
            lines.append("Handoff actions:")
            for a in ctx["last_session_baton"]["next_actions"]:
                lines.append(f"  - {a}")

    tq = ctx["task_queue"]
    if tq["total_active"] > 0:
        lines.append("")
        lines.append(f"--- TASK QUEUE ({tq['total_active']} active) ---")
        if tq["blocked"]:
            lines.append(f"BLOCKED ({len(tq['blocked'])}):")
            for t in tq["blocked"]:
                lines.append(f"  ! P{t['priority']} {t['title']} [{t['id'][:8]}]")
        if tq["in_progress"]:
            lines.append(f"IN PROGRESS ({len(tq['in_progress'])}):")
            for t in tq["in_progress"]:
                lines.append(f"  > P{t['priority']} {t['title']} [{t['id'][:8]}]")
        if tq["verification"]:
            lines.append(f"VERIFICATION ({len(tq['verification'])}):")
            for t in tq["verification"]:
                lines.append(f"  ? P{t['priority']} {t['title']} [{t['id'][:8]}]")
        if tq["ready"]:
            lines.append(f"READY ({len(tq['ready'])}):")
            for t in tq["ready"][:5]:
                lines.append(f"  . P{t['priority']} {t['title']} [{t['id'][:8]}]")

    lines.append("")
    lines.append("--- DIRECTIVES ---")
    for d in ctx["directives"]:
        lines.append(f"  [{d['category']}] {d['directive'][:120]}...")

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)
