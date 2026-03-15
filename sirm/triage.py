import json
import re
from typing import Optional
from sirm.models import _now


DEFAULT_TRIAGE_RULES = [
    {
        "id": "security_critical",
        "name": "Security Issue",
        "pattern": "security|vulnerabilit|CVE|exploit|injection|XSS|CSRF|auth bypass",
        "match_fields": ["title", "description"],
        "assignments": {
            "priority": 1,
            "role": "quality_overlay",
            "stage": "code",
            "tags": ["security"]
        },
        "enabled": True
    },
    {
        "id": "bug_fix",
        "name": "Bug Fix",
        "pattern": "bug|fix|broken|crash|error|exception|failure|regression",
        "match_fields": ["title", "description"],
        "assignments": {
            "priority": 2,
            "role": "line_worker",
            "stage": "code",
            "tags": ["bug"]
        },
        "enabled": True
    },
    {
        "id": "hotfix",
        "name": "Hotfix",
        "pattern": "hotfix|urgent|critical|emergency|outage|incident",
        "match_fields": ["title", "description"],
        "assignments": {
            "priority": 1,
            "role": "line_worker",
            "stage": "code",
            "tags": ["hotfix"]
        },
        "enabled": True
    },
    {
        "id": "refactor",
        "name": "Refactor",
        "pattern": "refactor|cleanup|clean up|reorganize|restructure|tech debt",
        "match_fields": ["title", "description"],
        "assignments": {
            "priority": 4,
            "role": "line_worker",
            "stage": "code",
            "tags": ["refactor"]
        },
        "enabled": True
    },
    {
        "id": "infrastructure",
        "name": "Infrastructure",
        "pattern": "infra|infrastructure|deploy|CI/CD|pipeline|docker|kubernetes|monitoring|observability",
        "match_fields": ["title", "description"],
        "assignments": {
            "priority": 3,
            "role": "line_worker",
            "stage": "operate",
            "tags": ["infrastructure"]
        },
        "enabled": True
    },
    {
        "id": "feature",
        "name": "Feature",
        "pattern": "feature|add|implement|create|build|new",
        "match_fields": ["title"],
        "assignments": {
            "priority": 3,
            "role": "line_worker",
            "stage": "plan",
            "tags": ["feature"]
        },
        "enabled": True
    },
    {
        "id": "documentation",
        "name": "Documentation",
        "pattern": "doc|documentation|readme|guide|tutorial|API docs",
        "match_fields": ["title", "description"],
        "assignments": {
            "priority": 4,
            "role": "line_worker",
            "stage": "plan",
            "tags": ["documentation"]
        },
        "enabled": True
    },
    {
        "id": "testing",
        "name": "Testing",
        "pattern": "test|testing|coverage|spec|e2e|integration test|unit test",
        "match_fields": ["title", "description"],
        "assignments": {
            "priority": 3,
            "role": "quality_overlay",
            "stage": "code",
            "tags": ["testing"]
        },
        "enabled": True
    },
]

VALID_STATUSES = {"backlog", "ready", "in_progress", "verification", "done", "blocked"}
VALID_STAGES = {"plan", "code", "build", "integrate", "release", "operate"}
VALID_ROLES = {"line_worker", "line_manager", "assembly_manager", "factory_manager", "quality_overlay", "plant_governance"}


class TriageEngine:
    def __init__(self, store):
        self.store = store

    def get_rules(self):
        try:
            config = self.store.get_config()
            config_dict = config.to_dict()
            rules_json = None
            if hasattr(self.store, '_conn'):
                conn = self.store._conn()
                row = conn.execute("SELECT value FROM config WHERE key = 'triage_rules'").fetchone()
                conn.close()
                if row:
                    rules_json = row["value"] if isinstance(row["value"], str) else row[0]
            if rules_json:
                return json.loads(rules_json)
        except Exception:
            pass
        return list(DEFAULT_TRIAGE_RULES)

    def save_rules(self, rules):
        if hasattr(self.store, '_conn'):
            conn = self.store._conn()
            conn.execute(
                "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
                ("triage_rules", json.dumps(rules, default=str))
            )
            conn.commit()
            conn.close()

    def add_rule(self, rule_data):
        rules = self.get_rules()
        rule = {
            "id": rule_data.get("id", "rule_" + _now().replace(":", "").replace("-", "")[:12]),
            "name": rule_data.get("name", ""),
            "pattern": rule_data.get("pattern", ""),
            "match_fields": rule_data.get("match_fields", ["title", "description"]),
            "assignments": {
                "priority": int(rule_data.get("priority", 3)),
                "role": rule_data.get("role", "line_worker"),
                "stage": rule_data.get("stage", "plan"),
                "tags": [t.strip() for t in rule_data.get("tags", "").split(",") if t.strip()] if isinstance(rule_data.get("tags"), str) else rule_data.get("tags", []),
            },
            "enabled": True
        }
        if rule["assignments"]["role"] not in VALID_ROLES:
            rule["assignments"]["role"] = "line_worker"
        if rule["assignments"]["stage"] not in VALID_STAGES:
            rule["assignments"]["stage"] = "plan"
        rule["assignments"]["priority"] = max(1, min(5, rule["assignments"]["priority"]))
        rules.append(rule)
        self.save_rules(rules)
        return rule

    def delete_rule(self, rule_id):
        rules = self.get_rules()
        rules = [r for r in rules if r.get("id") != rule_id]
        self.save_rules(rules)

    def toggle_rule(self, rule_id):
        rules = self.get_rules()
        for rule in rules:
            if rule.get("id") == rule_id:
                rule["enabled"] = not rule.get("enabled", True)
                break
        self.save_rules(rules)

    def apply_rules(self, title, description=""):
        rules = self.get_rules()
        suggestions = {
            "matched_rules": [],
            "priority": None,
            "role": None,
            "stage": None,
            "tags": [],
        }

        for rule in rules:
            if not rule.get("enabled", True):
                continue
            pattern = rule.get("pattern", "")
            if not pattern:
                continue

            match_fields = rule.get("match_fields", ["title", "description"])
            text_parts = []
            if "title" in match_fields:
                text_parts.append(title or "")
            if "description" in match_fields:
                text_parts.append(description or "")
            combined_text = " ".join(text_parts).lower()

            try:
                if re.search(pattern, combined_text, re.IGNORECASE):
                    assignments = rule.get("assignments", {})
                    suggestions["matched_rules"].append(rule)

                    if suggestions["priority"] is None or assignments.get("priority", 3) < suggestions["priority"]:
                        suggestions["priority"] = assignments.get("priority", 3)

                    if suggestions["role"] is None:
                        suggestions["role"] = assignments.get("role", "line_worker")

                    if suggestions["stage"] is None:
                        suggestions["stage"] = assignments.get("stage", "plan")

                    for tag in assignments.get("tags", []):
                        if tag not in suggestions["tags"]:
                            suggestions["tags"].append(tag)
            except re.error:
                continue

        return suggestions

    def apply_to_task(self, task):
        suggestions = self.apply_rules(task.title, task.description)
        applied = []

        if suggestions["priority"] is not None:
            task.priority = suggestions["priority"]
            applied.append(f"priority=P{task.priority}")

        if suggestions["role"] is not None:
            task.role = suggestions["role"]
            applied.append(f"role={task.role}")

        if suggestions["stage"] is not None:
            task.stage = suggestions["stage"]
            applied.append(f"stage={task.stage}")

        if suggestions["tags"]:
            for tag in suggestions["tags"]:
                if tag not in task.tags:
                    task.tags.append(tag)
            applied.append(f"tags={','.join(suggestions['tags'])}")

        if applied:
            rule_names = [r["name"] for r in suggestions["matched_rules"]]
            task.add_activity(
                "auto_triage",
                f"Auto-triage applied: {'; '.join(applied)}. Matched rules: {', '.join(rule_names)}"
            )

        return suggestions
