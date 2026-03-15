"""
SIRM Central API — The single brain for all agents across all environments.

Local agents, Replit agents, CI/CD, webhooks — everything calls this API.
All data lives in one PostgreSQL database. One source of truth.

Authentication: X-API-Key header checked against SIRM_API_KEY env var.
If SIRM_API_KEY is not set, API is open (development mode).

Routes:
  POST /api/sirm/checkin       — Worker checks in, gets briefing
  POST /api/sirm/checkout      — Worker checks out, writes baton
  POST /api/sirm/heartbeat     — Worker heartbeat
  GET  /api/sirm/briefing      — Get current session briefing
  GET  /api/sirm/directives    — Get all active directives
  POST /api/sirm/directive     — Add a directive
  GET  /api/sirm/contracts     — Get all enforced contracts
  GET  /api/sirm/context       — Get all context entries
  POST /api/sirm/context       — Set a context entry
  GET  /api/sirm/tasks         — Get active task queue
  GET  /api/sirm/memories      — Get recent memories
  POST /api/sirm/memory        — Add a memory
  POST /api/sirm/chat          — Log a chat message
  GET  /api/sirm/chat/<sid>    — Get chat log for a session
  GET  /api/sirm/workers       — Get all registered workers
  GET  /api/sirm/sprints       — Get active sprints
  POST /api/sirm/sprint        — Create/update a sprint
  GET  /api/sirm/state         — Full factory state dump
"""

import os
import json
import logging
from datetime import datetime, timezone
from functools import wraps
from flask import Blueprint, request, jsonify
import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

central_bp = Blueprint("central_api", __name__, url_prefix="/api/sirm")

DATABASE_URL = os.environ.get("DATABASE_URL", "")
SIRM_API_KEY = os.environ.get("SIRM_API_KEY", "")


def _conn():
    return psycopg2.connect(DATABASE_URL)


def _require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not SIRM_API_KEY:
            return f(*args, **kwargs)
        key = request.headers.get("X-API-Key", "")
        if key != SIRM_API_KEY:
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


@central_bp.route("/checkin", methods=["POST"])
@_require_auth
def checkin():
    data = request.get_json(silent=True) or {}
    worker_id = data.get("worker_id", "").strip()
    if not worker_id:
        return jsonify({"error": "worker_id required"}), 400

    worker_type = data.get("worker_type", "replit_agent")
    repl_name = data.get("repl_name", "")
    environment = data.get("environment", "replit")
    capabilities = json.dumps(data.get("capabilities", []))
    session_id = data.get("session_id", "")

    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO agent_workers (id, worker_type, repl_name, environment, status,
                current_session_id, capabilities, last_heartbeat, last_checkin)
            VALUES (%s, %s, %s, %s, 'active', %s, %s, NOW(), NOW())
            ON CONFLICT (id) DO UPDATE SET
                status = 'active',
                worker_type = EXCLUDED.worker_type,
                repl_name = EXCLUDED.repl_name,
                environment = EXCLUDED.environment,
                current_session_id = EXCLUDED.current_session_id,
                capabilities = EXCLUDED.capabilities,
                last_heartbeat = NOW(),
                last_checkin = NOW()
        """, (worker_id, worker_type, repl_name, environment, session_id, capabilities))
        conn.commit()

        from sirm.agent_memory import load_session_context, format_briefing
        ctx = load_session_context()
        briefing = format_briefing(ctx)

        return jsonify({
            "status": "checked_in",
            "worker_id": worker_id,
            "briefing": briefing,
            "top_action": ctx["top_action"],
            "top_task": ctx.get("top_task"),
            "task_queue": ctx["task_queue"],
            "directives": ctx["directives"],
            "last_session_baton": ctx["last_session_baton"],
        })
    finally:
        conn.close()


@central_bp.route("/checkout", methods=["POST"])
@_require_auth
def checkout():
    data = request.get_json(silent=True) or {}
    worker_id = data.get("worker_id", "").strip()
    if not worker_id:
        return jsonify({"error": "worker_id required"}), 400

    session_id = data.get("session_id", "")
    summary = data.get("summary", "")
    tasks_completed = data.get("tasks_completed", [])
    tasks_started = data.get("tasks_started", [])
    decisions_made = data.get("decisions_made", [])
    next_actions = data.get("next_actions", [])
    escalations = data.get("escalations", [])

    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE agent_workers SET
                status = 'offline',
                last_checkout = NOW(),
                checkout_summary = %s,
                current_task_id = NULL,
                current_session_id = NULL
            WHERE id = %s
        """, (summary, worker_id))

        if session_id:
            cur.execute("""
                INSERT INTO agent_sessions (session_id, repl_name, started_at, ended_at,
                    summary, tasks_completed, tasks_started, decisions_made, escalations, next_actions)
                VALUES (%s, %s, NOW(), NOW(), %s, %s, %s, %s, %s, %s)
            """, (
                session_id, data.get("repl_name", ""), summary,
                json.dumps(tasks_completed), json.dumps(tasks_started),
                json.dumps(decisions_made), json.dumps(escalations), json.dumps(next_actions),
            ))

        conn.commit()
        return jsonify({"status": "checked_out", "worker_id": worker_id})
    finally:
        conn.close()


@central_bp.route("/heartbeat", methods=["POST"])
@_require_auth
def heartbeat():
    data = request.get_json(silent=True) or {}
    worker_id = data.get("worker_id", "").strip()
    if not worker_id:
        return jsonify({"error": "worker_id required"}), 400

    conn = _conn()
    try:
        cur = conn.cursor()
        updates = ["last_heartbeat = NOW()"]
        params = []
        if "current_task_id" in data:
            updates.append("current_task_id = %s")
            params.append(data["current_task_id"])
        if "status" in data:
            updates.append("status = %s")
            params.append(data["status"])
        params.append(worker_id)
        cur.execute(f"UPDATE agent_workers SET {', '.join(updates)} WHERE id = %s", params)
        conn.commit()
        return jsonify({"status": "ok"})
    finally:
        conn.close()


@central_bp.route("/briefing", methods=["GET"])
@_require_auth
def briefing():
    from sirm.agent_memory import load_session_context, format_briefing
    ctx = load_session_context()
    fmt = request.args.get("format", "json")
    if fmt == "text":
        return format_briefing(ctx), 200, {"Content-Type": "text/plain"}
    return jsonify(ctx)


@central_bp.route("/directives", methods=["GET"])
@_require_auth
def get_directives():
    conn = _conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM agent_directives WHERE active = TRUE ORDER BY priority, id")
        return jsonify([dict(r) for r in cur.fetchall()])
    finally:
        conn.close()


@central_bp.route("/directive", methods=["POST"])
@_require_auth
def add_directive():
    data = request.get_json(silent=True) or {}
    directive = data.get("directive", "").strip()
    if not directive:
        return jsonify({"error": "directive required"}), 400

    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO agent_directives (directive, priority, category, source) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (directive, data.get("priority", 2), data.get("category", "general"), data.get("source", "api"))
        )
        row = cur.fetchone()
        conn.commit()
        return jsonify({"id": row[0], "status": "created"})
    finally:
        conn.close()


@central_bp.route("/contracts", methods=["GET"])
@_require_auth
def get_contracts():
    conn = _conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        enforced_only = request.args.get("enforced", "true").lower() == "true"
        if enforced_only:
            cur.execute("SELECT * FROM agent_contracts WHERE enforced = TRUE ORDER BY category, contract_name")
        else:
            cur.execute("SELECT * FROM agent_contracts ORDER BY category, contract_name")
        return jsonify([dict(r) for r in cur.fetchall()])
    finally:
        conn.close()


@central_bp.route("/context", methods=["GET"])
@_require_auth
def get_context():
    conn = _conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        category = request.args.get("category")
        if category:
            cur.execute("SELECT * FROM agent_context WHERE category = %s ORDER BY context_key", (category,))
        else:
            cur.execute("SELECT * FROM agent_context ORDER BY category, context_key")
        return jsonify([dict(r) for r in cur.fetchall()])
    finally:
        conn.close()


@central_bp.route("/context", methods=["POST"])
@_require_auth
def set_context():
    data = request.get_json(silent=True) or {}
    key = data.get("key", "").strip()
    value = data.get("value", "").strip()
    if not key or not value:
        return jsonify({"error": "key and value required"}), 400

    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO agent_context (context_key, context_value, category)
            VALUES (%s, %s, %s)
            ON CONFLICT (context_key) DO UPDATE SET
                context_value = EXCLUDED.context_value, category = EXCLUDED.category, updated_at = NOW()
        """, (key, value, data.get("category", "operational")))
        conn.commit()
        return jsonify({"status": "set", "key": key})
    finally:
        conn.close()


@central_bp.route("/tasks", methods=["GET"])
@_require_auth
def get_tasks():
    conn = _conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        status_filter = request.args.get("status")
        if status_filter:
            cur.execute(
                "SELECT id, title, status, priority, stage, description, assigned_to, tags, updated_at "
                "FROM sirm_tasks WHERE status = %s ORDER BY priority, updated_at DESC",
                (status_filter,)
            )
        else:
            cur.execute(
                "SELECT id, title, status, priority, stage, description, assigned_to, tags, updated_at "
                "FROM sirm_tasks WHERE status != 'done' ORDER BY priority, "
                "CASE status WHEN 'blocked' THEN 0 WHEN 'in_progress' THEN 1 "
                "WHEN 'verification' THEN 2 WHEN 'ready' THEN 3 ELSE 4 END, updated_at DESC"
            )
        return jsonify([dict(r) for r in cur.fetchall()])
    finally:
        conn.close()


@central_bp.route("/memories", methods=["GET"])
@_require_auth
def get_memories():
    conn = _conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        limit = min(int(request.args.get("limit", 20)), 100)
        category = request.args.get("category")
        if category:
            cur.execute(
                "SELECT * FROM sirm_memories WHERE category = %s ORDER BY created_at DESC LIMIT %s",
                (category, limit)
            )
        else:
            cur.execute("SELECT * FROM sirm_memories ORDER BY created_at DESC LIMIT %s", (limit,))
        return jsonify([dict(r) for r in cur.fetchall()])
    finally:
        conn.close()


@central_bp.route("/memory", methods=["POST"])
@_require_auth
def add_memory():
    data = request.get_json(silent=True) or {}
    content = data.get("content", "").strip()
    if not content:
        return jsonify({"error": "content required"}), 400

    from sirm.models import _new_id, _now
    conn = _conn()
    try:
        cur = conn.cursor()
        mid = _new_id()
        cur.execute(
            "INSERT INTO sirm_memories (id, category, content, source, tags, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (mid, data.get("category", "operational"), content,
             data.get("source", "api"), json.dumps(data.get("tags", [])), _now())
        )
        conn.commit()
        return jsonify({"id": mid, "status": "created"})
    finally:
        conn.close()


@central_bp.route("/chat", methods=["POST"])
@_require_auth
def log_chat():
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "").strip()
    content = data.get("content", "").strip()
    if not session_id or not content:
        return jsonify({"error": "session_id and content required"}), 400

    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO agent_chat_log (session_id, worker_id, role, content, source, repl_name, metadata) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (
                session_id,
                data.get("worker_id", ""),
                data.get("role", "assistant"),
                content,
                data.get("source", "api"),
                data.get("repl_name", ""),
                json.dumps(data.get("metadata", {})),
            )
        )
        row = cur.fetchone()
        conn.commit()
        return jsonify({"id": row[0], "status": "logged"})
    finally:
        conn.close()


@central_bp.route("/chat/<session_id>", methods=["GET"])
@_require_auth
def get_chat_log(session_id):
    conn = _conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT * FROM agent_chat_log WHERE session_id = %s ORDER BY created_at",
            (session_id,)
        )
        rows = cur.fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@central_bp.route("/workers", methods=["GET"])
@_require_auth
def get_workers():
    conn = _conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM agent_workers ORDER BY last_heartbeat DESC NULLS LAST")
        return jsonify([dict(r) for r in cur.fetchall()])
    finally:
        conn.close()


@central_bp.route("/sprints", methods=["GET"])
@_require_auth
def get_sprints():
    conn = _conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM agent_sprints WHERE status = 'active' ORDER BY started_at DESC")
        return jsonify([dict(r) for r in cur.fetchall()])
    finally:
        conn.close()


@central_bp.route("/sprint", methods=["POST"])
@_require_auth
def create_sprint():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400

    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO agent_sprints (sprint_name, goal, linear_project_id, task_ids) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (name, data.get("goal", ""), data.get("linear_project_id", ""),
             json.dumps(data.get("task_ids", [])))
        )
        row = cur.fetchone()
        conn.commit()
        return jsonify({"id": row[0], "status": "created"})
    finally:
        conn.close()


@central_bp.route("/state", methods=["GET"])
@_require_auth
def full_state():
    from sirm.agent_memory import load_session_context
    ctx = load_session_context()

    conn = _conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("SELECT * FROM agent_contracts WHERE enforced = TRUE ORDER BY category")
        contracts = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT * FROM agent_workers ORDER BY last_heartbeat DESC NULLS LAST")
        workers = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT * FROM agent_sprints WHERE status = 'active'")
        sprints = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT count(*) as total FROM agent_chat_log")
        chat_count = cur.fetchone()["total"]

        return jsonify({
            "briefing": ctx,
            "contracts": contracts,
            "workers": workers,
            "sprints": sprints,
            "chat_log_count": chat_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    finally:
        conn.close()


@central_bp.route("/swarm/factory", methods=["GET"])
@_require_auth
def swarm_factory_status():
    from sirm.swarm import swarm
    return jsonify(swarm.get_factory_status())


@central_bp.route("/swarm/sprint", methods=["POST"])
@_require_auth
def swarm_create_sprint():
    from sirm.swarm import swarm
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    result = swarm.create_sprint(
        name=name,
        goal=data.get("goal", ""),
        strategy=data.get("strategy", "parallel"),
        max_workers=data.get("max_workers", 10),
        task_filter=data.get("task_filter"),
    )
    return jsonify(result)


@central_bp.route("/swarm/sprint/<int:sprint_id>/launch", methods=["POST"])
@_require_auth
def swarm_launch_sprint(sprint_id):
    from sirm.swarm import swarm
    return jsonify(swarm.launch_sprint(sprint_id))


@central_bp.route("/swarm/sprint/<int:sprint_id>/status", methods=["GET"])
@_require_auth
def swarm_sprint_status(sprint_id):
    from sirm.swarm import swarm
    return jsonify(swarm.get_sprint_status(sprint_id))


@central_bp.route("/swarm/dispatch", methods=["POST"])
@_require_auth
def swarm_dispatch():
    from sirm.swarm import swarm
    data = request.get_json(silent=True) or {}
    sprint_id = data.get("sprint_id")
    return jsonify(swarm.dispatch_tasks(sprint_id))


@central_bp.route("/swarm/queue/<worker_id>", methods=["GET"])
@_require_auth
def swarm_worker_queue(worker_id):
    from sirm.swarm import swarm
    return jsonify(swarm.get_worker_queue(worker_id))


@central_bp.route("/swarm/start/<int:dispatch_id>", methods=["POST"])
@_require_auth
def swarm_start_work(dispatch_id):
    from sirm.swarm import swarm
    data = request.get_json(silent=True) or {}
    worker_id = data.get("worker_id", "").strip()
    if not worker_id:
        return jsonify({"error": "worker_id required"}), 400
    return jsonify(swarm.start_work(dispatch_id, worker_id))


@central_bp.route("/swarm/complete/<int:dispatch_id>", methods=["POST"])
@_require_auth
def swarm_complete(dispatch_id):
    from sirm.swarm import swarm
    data = request.get_json(silent=True) or {}
    worker_id = data.get("worker_id", "").strip()
    if not worker_id:
        return jsonify({"error": "worker_id required"}), 400
    return jsonify(swarm.complete_dispatch(
        dispatch_id, worker_id,
        result=data.get("result", ""),
        status=data.get("status", "completed")
    ))


@central_bp.route("/swarm/escalate/<int:dispatch_id>", methods=["POST"])
@_require_auth
def swarm_escalate(dispatch_id):
    from sirm.swarm import swarm
    data = request.get_json(silent=True) or {}
    worker_id = data.get("worker_id", "").strip()
    reason = data.get("reason", "").strip()
    if not worker_id or not reason:
        return jsonify({"error": "worker_id and reason required"}), 400
    return jsonify(swarm.escalate(dispatch_id, reason, worker_id))


@central_bp.route("/swarm/monitor", methods=["POST"])
@_require_auth
def swarm_monitor():
    from sirm.swarm import swarm
    data = request.get_json(silent=True) or {}
    threshold = data.get("stale_threshold_minutes", 5)
    return jsonify(swarm.monitor_heartbeats(threshold))


@central_bp.route("/swarm/messages", methods=["GET"])
@_require_auth
def swarm_get_messages():
    from sirm.swarm import swarm
    worker_id = request.args.get("worker_id", "")
    if not worker_id:
        return jsonify({"error": "worker_id required"}), 400
    unread = request.args.get("unread", "true").lower() == "true"
    channel = request.args.get("channel")
    return jsonify(swarm.get_messages(worker_id, unread, channel))


@central_bp.route("/swarm/message", methods=["POST"])
@_require_auth
def swarm_send_message():
    from sirm.swarm import swarm
    data = request.get_json(silent=True) or {}
    required = ["from_worker", "subject", "body"]
    for f in required:
        if not data.get(f, "").strip():
            return jsonify({"error": f"{f} required"}), 400
    return jsonify(swarm.send_message(
        from_worker=data["from_worker"],
        to_worker=data.get("to_worker", "*"),
        channel=data.get("channel", "broadcast"),
        message_type=data.get("message_type", "info"),
        subject=data["subject"],
        body=data["body"],
        ref_task_id=data.get("ref_task_id", ""),
        ref_dispatch_id=data.get("ref_dispatch_id"),
    ))


@central_bp.route("/swarm/message/<int:message_id>/ack", methods=["POST"])
@_require_auth
def swarm_ack_message(message_id):
    from sirm.swarm import swarm
    data = request.get_json(silent=True) or {}
    worker_id = data.get("worker_id", "").strip()
    if not worker_id:
        return jsonify({"error": "worker_id required"}), 400
    return jsonify(swarm.ack_message(message_id, worker_id))


@central_bp.route("/swarm/hierarchy", methods=["GET"])
@_require_auth
def swarm_hierarchy():
    from sirm.swarm import ROLE_HIERARCHY, ROLE_CAPABILITIES
    return jsonify({
        "hierarchy": ROLE_HIERARCHY,
        "capabilities": ROLE_CAPABILITIES,
        "escalation_chain": {
            role: caps["escalates_to"]
            for role, caps in ROLE_CAPABILITIES.items()
        },
    })


@central_bp.route("/sync", methods=["POST"])
@_require_auth
def sync_upstream():
    from sirm.sync_upstream import sync_to_upstream
    data = request.get_json(silent=True) or {}
    force = data.get("force", False)
    dry_run = data.get("dry_run", False)
    result = sync_to_upstream(force=force, dry_run=dry_run)
    return jsonify(result)


@central_bp.route("/sync/status", methods=["GET"])
@_require_auth
def sync_status():
    from sirm.sync_upstream import check_sync_status
    return jsonify(check_sync_status())
