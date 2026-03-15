"""
SIRM Swarm Orchestration Engine — Multi-Agent Factory Floor

The swarm controller deploys, monitors, and coordinates multiple agents
working in parallel across the factory hierarchy. This is the core of
hyperscale execution: thousands of tasks, N agents, deterministic
priority ordering, role-based dispatch, escalation chains, and
real-time coordination through a shared communication bus.

Architecture:
                    ┌──────────────────┐
                    │ PLANT GOVERNANCE  │  Policy, compliance, strategic direction
                    └────────┬─────────┘
                             │ escalate
                    ┌────────▼─────────┐
                    │ FACTORY MANAGER   │  Orchestrates the swarm, deploys sprints
                    └────────┬─────────┘
                             │ delegate
                    ┌────────▼─────────┐
                    │ ASSEMBLY MANAGER  │  Coordinates across product lines
                    └────────┬─────────┘
                             │ assign
                    ┌────────▼─────────┐
                    │  LINE MANAGER     │  Supervises work streams
                    └────────┬─────────┘
                             │ dispatch
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │LINE WRKR │  │LINE WRKR │  │LINE WRKR │  Execute tasks
        └──────────┘  └──────────┘  └──────────┘

        ┌──────────────────────────────────────┐
        │         QUALITY OVERLAY              │  Horizontal: reviews all output
        └──────────────────────────────────────┘

Dispatch strategies:
  - parallel: Fan out all eligible tasks to available workers simultaneously
  - sequential: One task at a time, ordered by priority
  - pipeline: Stage-by-stage execution (plan→code→build→integrate→release→operate)
  - swarm: All workers attack a single complex task collaboratively

Sprint execution:
  1. Define sprint (goal, task filter, strategy, max workers)
  2. Controller fans out tasks to available workers by role
  3. Workers claim, execute, report back
  4. Controller monitors heartbeats, detects stale workers, reassigns
  5. Escalation chain fires when workers hit blockers
  6. Sprint completes when all dispatched tasks are done/failed
"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")

ROLE_HIERARCHY = [
    "line_worker",
    "quality_overlay",
    "line_manager",
    "assembly_manager",
    "factory_manager",
    "plant_governance",
]

ROLE_CAPABILITIES = {
    "line_worker": {
        "can_execute": True,
        "can_review": False,
        "can_dispatch": False,
        "can_escalate": True,
        "can_override_gates": False,
        "max_concurrent_tasks": 1,
        "escalates_to": "line_manager",
    },
    "quality_overlay": {
        "can_execute": True,
        "can_review": True,
        "can_dispatch": False,
        "can_escalate": True,
        "can_override_gates": False,
        "max_concurrent_tasks": 3,
        "escalates_to": "assembly_manager",
    },
    "line_manager": {
        "can_execute": True,
        "can_review": True,
        "can_dispatch": True,
        "can_escalate": True,
        "can_override_gates": False,
        "max_concurrent_tasks": 2,
        "escalates_to": "assembly_manager",
    },
    "assembly_manager": {
        "can_execute": True,
        "can_review": True,
        "can_dispatch": True,
        "can_escalate": True,
        "can_override_gates": True,
        "max_concurrent_tasks": 5,
        "escalates_to": "factory_manager",
    },
    "factory_manager": {
        "can_execute": True,
        "can_review": True,
        "can_dispatch": True,
        "can_escalate": True,
        "can_override_gates": True,
        "max_concurrent_tasks": 10,
        "escalates_to": "plant_governance",
    },
    "plant_governance": {
        "can_execute": False,
        "can_review": True,
        "can_dispatch": True,
        "can_escalate": False,
        "can_override_gates": True,
        "max_concurrent_tasks": 0,
        "escalates_to": None,
    },
}

DISPATCH_STRATEGIES = ["parallel", "sequential", "pipeline", "swarm"]

DISPATCH_STATUSES = ["queued", "claimed", "running", "completed", "failed", "escalated", "timeout", "cancelled"]


def _conn():
    return psycopg2.connect(DATABASE_URL)


def _now():
    return datetime.now(timezone.utc).isoformat()


class SwarmController:

    def create_sprint(self, name: str, goal: str = "", strategy: str = "parallel",
                      max_workers: int = 10, task_filter: Optional[dict] = None) -> dict:
        conn = _conn()
        try:
            cur = conn.cursor()
            tf = json.dumps(task_filter or {})
            cur.execute(
                "INSERT INTO swarm_sprints (name, goal, strategy, max_concurrent_workers, task_filter) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (name, goal, strategy, max_workers, tf)
            )
            sprint_id = cur.fetchone()[0]
            conn.commit()
            logger.info(f"Sprint {sprint_id} created: {name} ({strategy}, max {max_workers} workers)")
            return {"sprint_id": sprint_id, "name": name, "strategy": strategy}
        finally:
            conn.close()

    def launch_sprint(self, sprint_id: int) -> dict:
        conn = _conn()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT * FROM swarm_sprints WHERE id = %s", (sprint_id,))
            sprint = cur.fetchone()
            if not sprint:
                return {"error": "sprint not found"}
            if sprint["status"] not in ("planning", "paused"):
                return {"error": f"sprint is {sprint['status']}, cannot launch"}

            task_filter = sprint["task_filter"] or {}
            query = "SELECT id, title, priority, role, stage, assigned_to FROM sirm_tasks WHERE status IN ('ready', 'backlog')"
            params = []

            if task_filter.get("status"):
                query += " AND status = %s"
                params.append(task_filter["status"])
            if task_filter.get("priority_max"):
                query += " AND priority <= %s"
                params.append(task_filter["priority_max"])
            if task_filter.get("stage"):
                query += " AND stage = %s"
                params.append(task_filter["stage"])
            if task_filter.get("role"):
                query += " AND role = %s"
                params.append(task_filter["role"])
            if task_filter.get("tags"):
                query += " AND tags ?| %s"
                params.append(task_filter["tags"])

            query += " ORDER BY priority, created_at"
            cur.execute(query, params)
            tasks = cur.fetchall()

            dispatched = 0
            for task in tasks:
                cur.execute(
                    "INSERT INTO swarm_dispatch (sprint_id, task_id, assigned_role, priority, status) "
                    "VALUES (%s, %s, %s, %s, 'queued')",
                    (sprint_id, task["id"], task.get("role", "line_worker"), task["priority"])
                )
                dispatched += 1

            cur.execute(
                "UPDATE swarm_sprints SET status = 'active', started_at = NOW(), total_tasks = %s WHERE id = %s",
                (dispatched, sprint_id)
            )
            conn.commit()

            logger.info(f"Sprint {sprint_id} launched: {dispatched} tasks dispatched")
            return {"sprint_id": sprint_id, "dispatched": dispatched, "status": "active"}
        finally:
            conn.close()

    def dispatch_tasks(self, sprint_id: Optional[int] = None) -> dict:
        conn = _conn()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            cur.execute(
                "SELECT * FROM agent_workers WHERE status = 'active' "
                "AND last_heartbeat > NOW() - INTERVAL '5 minutes' "
                "ORDER BY last_heartbeat DESC"
            )
            active_workers = cur.fetchall()

            if not active_workers:
                return {"dispatched": 0, "reason": "no active workers"}

            query = "SELECT * FROM swarm_dispatch WHERE status = 'queued'"
            params = []
            if sprint_id:
                query += " AND sprint_id = %s"
                params.append(sprint_id)
            query += " ORDER BY priority, created_at LIMIT 100"
            cur.execute(query, params)
            queued = cur.fetchall()

            worker_loads = {}
            for w in active_workers:
                cur.execute(
                    "SELECT count(*) FROM swarm_dispatch WHERE assigned_worker_id = %s AND status IN ('claimed', 'running')",
                    (w["id"],)
                )
                load = cur.fetchone()["count"]
                role = self._get_worker_role(w)
                max_tasks = ROLE_CAPABILITIES.get(role, {}).get("max_concurrent_tasks", 1)
                worker_loads[w["id"]] = {"worker": w, "load": load, "max": max_tasks, "role": role}

            dispatched = 0
            for d in queued:
                best_worker = self._find_best_worker(d, worker_loads)
                if not best_worker:
                    continue

                cur.execute(
                    "UPDATE swarm_dispatch SET assigned_worker_id = %s, status = 'claimed', claimed_at = NOW() "
                    "WHERE id = %s AND status = 'queued' "
                    "AND id = (SELECT id FROM swarm_dispatch WHERE id = %s AND status = 'queued' FOR UPDATE SKIP LOCKED)",
                    (best_worker, d["id"], d["id"])
                )
                if cur.rowcount > 0:
                    worker_loads[best_worker]["load"] += 1
                    dispatched += 1

            conn.commit()
            return {"dispatched": dispatched, "queued_remaining": len(queued) - dispatched}
        finally:
            conn.close()

    def _get_worker_role(self, worker: dict) -> str:
        caps = worker.get("capabilities", "[]")
        if isinstance(caps, str):
            try:
                caps = json.loads(caps)
            except (json.JSONDecodeError, TypeError):
                caps = []
        for role in reversed(ROLE_HIERARCHY):
            if role in caps:
                return role
        return "line_worker"

    def _find_best_worker(self, dispatch: dict, worker_loads: dict) -> Optional[str]:
        required_role = dispatch.get("assigned_role", "line_worker")
        required_idx = ROLE_HIERARCHY.index(required_role) if required_role in ROLE_HIERARCHY else 0

        candidates = []
        for wid, info in worker_loads.items():
            if info["load"] >= info["max"]:
                continue
            worker_role_idx = ROLE_HIERARCHY.index(info["role"]) if info["role"] in ROLE_HIERARCHY else 0
            if worker_role_idx >= required_idx:
                candidates.append((wid, info["load"], worker_role_idx))

        if not candidates:
            return None

        candidates.sort(key=lambda c: (abs(c[2] - required_idx), c[1]))
        return candidates[0][0]

    def escalate(self, dispatch_id: int, reason: str, worker_id: str) -> dict:
        conn = _conn()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT * FROM swarm_dispatch WHERE id = %s", (dispatch_id,))
            d = cur.fetchone()
            if not d:
                return {"error": "dispatch not found"}
            if d.get("assigned_worker_id") and d["assigned_worker_id"] != worker_id:
                return {"error": "only the assigned worker can escalate"}

            current_role = d.get("assigned_role", "line_worker")
            caps = ROLE_CAPABILITIES.get(current_role, {})
            if not caps.get("can_escalate"):
                return {"error": f"role {current_role} cannot escalate"}
            next_role = caps.get("escalates_to")
            if not next_role:
                return {"error": f"no escalation target from {current_role}"}

            cur.execute(
                "UPDATE swarm_dispatch SET status = 'escalated', error = %s WHERE id = %s",
                (reason, dispatch_id)
            )

            cur.execute(
                "INSERT INTO swarm_dispatch (sprint_id, task_id, assigned_role, priority, status, "
                "parent_dispatch_id, escalated_from, escalated_reason) "
                "VALUES (%s, %s, %s, %s, 'queued', %s, %s, %s) RETURNING id",
                (d["sprint_id"], d["task_id"], next_role,
                 max(1, d["priority"] - 1),
                 dispatch_id, worker_id, reason)
            )
            new_id = cur.fetchone()["id"]

            self._send_message(cur, worker_id, "*", "escalation",
                               f"Task {d['task_id']} escalated from {current_role} to {next_role}",
                               reason, d["task_id"], new_id)

            conn.commit()
            logger.info(f"Escalation: dispatch {dispatch_id} → {new_id} ({current_role} → {next_role})")
            return {"new_dispatch_id": new_id, "escalated_to": next_role, "from_role": current_role}
        finally:
            conn.close()

    def complete_dispatch(self, dispatch_id: int, worker_id: str, result: str = "",
                          status: str = "completed") -> dict:
        conn = _conn()
        try:
            cur = conn.cursor()
            valid = ("completed", "failed")
            if status not in valid:
                return {"error": f"status must be one of {valid}"}

            cur.execute(
                "UPDATE swarm_dispatch SET status = %s, completed_at = NOW(), result = %s "
                "WHERE id = %s AND assigned_worker_id = %s",
                (status, result, dispatch_id, worker_id)
            )
            if cur.rowcount == 0:
                conn.rollback()
                return {"error": "dispatch not found or not assigned to this worker"}

            cur.execute("SELECT sprint_id FROM swarm_dispatch WHERE id = %s", (dispatch_id,))
            row = cur.fetchone()
            if row and row[0]:
                sprint_id = row[0]
                field = "completed_tasks" if status == "completed" else "failed_tasks"
                cur.execute(
                    f"UPDATE swarm_sprints SET {field} = {field} + 1 WHERE id = %s",
                    (sprint_id,)
                )
                cur.execute(
                    "SELECT total_tasks, completed_tasks, failed_tasks FROM swarm_sprints WHERE id = %s",
                    (sprint_id,)
                )
                s = cur.fetchone()
                if s and (s[1] + s[2]) >= s[0]:
                    cur.execute(
                        "UPDATE swarm_sprints SET status = 'completed', completed_at = NOW() WHERE id = %s",
                        (sprint_id,)
                    )

            conn.commit()
            return {"dispatch_id": dispatch_id, "status": status}
        finally:
            conn.close()

    def monitor_heartbeats(self, stale_threshold_minutes: int = 5) -> dict:
        conn = _conn()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            threshold = datetime.now(timezone.utc) - timedelta(minutes=stale_threshold_minutes)

            cur.execute(
                "SELECT d.id as dispatch_id, d.task_id, d.assigned_worker_id, d.sprint_id, d.assigned_role, "
                "w.last_heartbeat, w.status as worker_status "
                "FROM swarm_dispatch d "
                "LEFT JOIN agent_workers w ON d.assigned_worker_id = w.id "
                "WHERE d.status IN ('claimed', 'running') "
                "AND (w.last_heartbeat IS NULL OR w.last_heartbeat < %s OR w.status != 'active')",
                (threshold,)
            )
            stale = cur.fetchall()

            reassigned = 0
            timed_out = 0
            for s in stale:
                cur.execute(
                    "SELECT retries, max_retries FROM swarm_dispatch WHERE id = %s",
                    (s["dispatch_id"],)
                )
                d_row = cur.fetchone()
                if d_row and d_row["retries"] < d_row["max_retries"]:
                    cur.execute(
                        "UPDATE swarm_dispatch SET status = 'queued', assigned_worker_id = NULL, "
                        "retries = retries + 1 WHERE id = %s",
                        (s["dispatch_id"],)
                    )
                    reassigned += 1
                else:
                    cur.execute(
                        "UPDATE swarm_dispatch SET status = 'timeout', error = 'Worker heartbeat lost, max retries exceeded' "
                        "WHERE id = %s",
                        (s["dispatch_id"],)
                    )
                    timed_out += 1

            conn.commit()
            return {"stale_detected": len(stale), "reassigned": reassigned, "timed_out": timed_out}
        finally:
            conn.close()

    def get_worker_queue(self, worker_id: str) -> list:
        conn = _conn()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT d.*, t.title, t.description, t.stage, t.tags, t.acceptance_criteria "
                "FROM swarm_dispatch d "
                "JOIN sirm_tasks t ON d.task_id = t.id "
                "WHERE d.assigned_worker_id = %s AND d.status IN ('claimed', 'running') "
                "ORDER BY d.priority, d.created_at",
                (worker_id,)
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def start_work(self, dispatch_id: int, worker_id: str) -> dict:
        conn = _conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE swarm_dispatch SET status = 'running', started_at = NOW() "
                "WHERE id = %s AND assigned_worker_id = %s AND status = 'claimed'",
                (dispatch_id, worker_id)
            )
            if cur.rowcount == 0:
                conn.rollback()
                return {"error": "dispatch not found, not assigned to you, or not in claimed status"}

            cur.execute("SELECT task_id FROM swarm_dispatch WHERE id = %s", (dispatch_id,))
            task_id = cur.fetchone()[0]
            cur.execute(
                "UPDATE sirm_tasks SET status = 'in_progress', assigned_to = %s, updated_at = NOW() "
                "WHERE id = %s AND status IN ('ready', 'backlog')",
                (worker_id, task_id)
            )
            cur.execute(
                "UPDATE agent_workers SET current_task_id = %s WHERE id = %s",
                (task_id, worker_id)
            )
            conn.commit()
            return {"dispatch_id": dispatch_id, "task_id": task_id, "status": "running"}
        finally:
            conn.close()

    def send_message(self, from_worker: str, to_worker: str, channel: str,
                     message_type: str, subject: str, body: str,
                     ref_task_id: str = "", ref_dispatch_id: Optional[int] = None) -> dict:
        conn = _conn()
        try:
            cur = conn.cursor()
            return self._send_message(cur, from_worker, to_worker, message_type, subject, body,
                                       ref_task_id, ref_dispatch_id, channel)
        finally:
            conn.commit()
            conn.close()

    def _send_message(self, cur, from_worker, to_worker, message_type, subject, body,
                      ref_task_id="", ref_dispatch_id=None, channel="broadcast"):
        cur.execute(
            "INSERT INTO swarm_messages (from_worker_id, to_worker_id, channel, message_type, "
            "subject, body, ref_task_id, ref_dispatch_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (from_worker, to_worker, channel, message_type, subject, body, ref_task_id, ref_dispatch_id)
        )
        return {"message_id": cur.fetchone()[0]}

    def get_messages(self, worker_id: str, unread_only: bool = True, channel: Optional[str] = None) -> list:
        conn = _conn()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            query = "SELECT * FROM swarm_messages WHERE (to_worker_id = %s OR to_worker_id = '*')"
            params = [worker_id]
            if unread_only:
                query += " AND acknowledged = FALSE"
            if channel:
                query += " AND channel = %s"
                params.append(channel)
            query += " ORDER BY created_at DESC LIMIT 50"
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def ack_message(self, message_id: int, worker_id: str) -> dict:
        conn = _conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE swarm_messages SET acknowledged = TRUE, ack_at = NOW() "
                "WHERE id = %s AND (to_worker_id = %s OR to_worker_id = '*')",
                (message_id, worker_id)
            )
            conn.commit()
            return {"acknowledged": cur.rowcount > 0}
        finally:
            conn.close()

    def get_sprint_status(self, sprint_id: int) -> dict:
        conn = _conn()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT * FROM swarm_sprints WHERE id = %s", (sprint_id,))
            sprint = cur.fetchone()
            if not sprint:
                return {"error": "sprint not found"}

            cur.execute(
                "SELECT status, count(*) as cnt FROM swarm_dispatch WHERE sprint_id = %s GROUP BY status",
                (sprint_id,)
            )
            status_counts = {r["status"]: r["cnt"] for r in cur.fetchall()}

            cur.execute(
                "SELECT d.assigned_worker_id, w.status as worker_status, w.last_heartbeat, "
                "count(*) as task_count "
                "FROM swarm_dispatch d "
                "LEFT JOIN agent_workers w ON d.assigned_worker_id = w.id "
                "WHERE d.sprint_id = %s AND d.status IN ('claimed', 'running') "
                "GROUP BY d.assigned_worker_id, w.status, w.last_heartbeat",
                (sprint_id,)
            )
            active_workers = [dict(r) for r in cur.fetchall()]

            total = sprint["total_tasks"] or 1
            progress = ((sprint["completed_tasks"] + sprint["failed_tasks"]) / total) * 100

            return {
                "sprint": dict(sprint),
                "status_breakdown": status_counts,
                "active_workers": active_workers,
                "progress_pct": round(progress, 1),
                "velocity": self._calc_velocity(cur, sprint_id),
            }
        finally:
            conn.close()

    def _calc_velocity(self, cur, sprint_id: int) -> dict:
        cur.execute(
            "SELECT count(*) as completed, "
            "EXTRACT(EPOCH FROM (max(completed_at) - min(started_at)))/60 as minutes_elapsed "
            "FROM swarm_dispatch WHERE sprint_id = %s AND status = 'completed'",
            (sprint_id,)
        )
        row = cur.fetchone()
        if not row or not row[1] or row[1] <= 0:
            return {"tasks_per_minute": 0, "estimated_remaining_minutes": 0}
        tpm = row[0] / row[1]
        cur.execute(
            "SELECT count(*) FROM swarm_dispatch WHERE sprint_id = %s AND status IN ('queued', 'claimed', 'running')",
            (sprint_id,)
        )
        remaining = cur.fetchone()[0]
        eta = remaining / tpm if tpm > 0 else 0
        return {"tasks_per_minute": round(tpm, 2), "estimated_remaining_minutes": round(eta, 1)}

    def get_factory_status(self) -> dict:
        conn = _conn()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            cur.execute("SELECT * FROM agent_workers ORDER BY last_heartbeat DESC NULLS LAST")
            workers = [dict(w) for w in cur.fetchall()]

            cur.execute("SELECT * FROM swarm_sprints WHERE status = 'active'")
            active_sprints = [dict(s) for s in cur.fetchall()]

            cur.execute(
                "SELECT status, count(*) as cnt FROM swarm_dispatch "
                "WHERE created_at > NOW() - INTERVAL '24 hours' GROUP BY status"
            )
            dispatch_24h = {r["status"]: r["cnt"] for r in cur.fetchall()}

            cur.execute(
                "SELECT assigned_role, status, count(*) as cnt FROM swarm_dispatch "
                "WHERE created_at > NOW() - INTERVAL '24 hours' GROUP BY assigned_role, status ORDER BY assigned_role"
            )
            role_breakdown = {}
            for r in cur.fetchall():
                role = r["assigned_role"]
                if role not in role_breakdown:
                    role_breakdown[role] = {}
                role_breakdown[role][r["status"]] = r["cnt"]

            cur.execute(
                "SELECT count(*) as cnt FROM swarm_messages WHERE created_at > NOW() - INTERVAL '24 hours'"
            )
            msg_count = cur.fetchone()["cnt"]

            cur.execute(
                "SELECT count(*) as cnt FROM swarm_dispatch WHERE status = 'escalated' "
                "AND created_at > NOW() - INTERVAL '24 hours'"
            )
            escalation_count = cur.fetchone()["cnt"]

            active_count = sum(1 for w in workers if w.get("status") == "active")
            now = datetime.now(timezone.utc)
            stale_threshold = now - timedelta(minutes=5)
            healthy_count = sum(1 for w in workers
                               if w.get("status") == "active" and w.get("last_heartbeat")
                               and w["last_heartbeat"].replace(tzinfo=timezone.utc if w["last_heartbeat"].tzinfo is None else w["last_heartbeat"].tzinfo) > stale_threshold)

            return {
                "workers": {
                    "total": len(workers),
                    "active": active_count,
                    "healthy": healthy_count,
                    "detail": workers,
                },
                "sprints": active_sprints,
                "dispatch_24h": dispatch_24h,
                "role_breakdown": role_breakdown,
                "messages_24h": msg_count,
                "escalations_24h": escalation_count,
                "hierarchy": ROLE_HIERARCHY,
                "capabilities": ROLE_CAPABILITIES,
                "timestamp": now.isoformat(),
            }
        finally:
            conn.close()


swarm = SwarmController()
