WORK_ORDER_TEMPLATES = {
    "bug_fix": {
        "name": "Bug Fix",
        "slug": "bug_fix",
        "description": "Fix a reported bug or defect",
        "defaults": {
            "title": "[BUG] ",
            "description": "## Bug Description\n\n## Steps to Reproduce\n1. \n2. \n3. \n\n## Expected Behavior\n\n## Actual Behavior\n\n## Root Cause Analysis\n",
            "status": "backlog",
            "stage": "code",
            "role": "line_worker",
            "priority": 2,
            "acceptance_criteria": [
                "Bug is no longer reproducible",
                "Root cause identified and documented",
                "Regression test added",
                "No new issues introduced",
            ],
            "security_considerations": "Review if bug has security implications. Check for data exposure or access control bypass.",
            "tags": ["bug", "fix"],
        },
    },
    "feature": {
        "name": "Feature",
        "slug": "feature",
        "description": "Build a new feature or capability",
        "defaults": {
            "title": "[FEATURE] ",
            "description": "## Objective\n\n## User Story\nAs a [role], I want [capability] so that [benefit].\n\n## Scope\n\n## Technical Approach\n\n## Out of Scope\n",
            "status": "backlog",
            "stage": "plan",
            "role": "line_worker",
            "priority": 3,
            "acceptance_criteria": [
                "Feature works as described in user story",
                "Unit tests cover new functionality",
                "Documentation updated",
                "Code reviewed and approved",
                "No performance regressions",
            ],
            "security_considerations": "Evaluate input validation, authentication/authorization requirements, and data handling for new feature.",
            "tags": ["feature"],
        },
    },
    "refactor": {
        "name": "Refactor",
        "slug": "refactor",
        "description": "Improve code structure without changing behavior",
        "defaults": {
            "title": "[REFACTOR] ",
            "description": "## Current State\n\n## Problems with Current Implementation\n\n## Proposed Changes\n\n## Migration Plan\n",
            "status": "backlog",
            "stage": "code",
            "role": "line_worker",
            "priority": 3,
            "acceptance_criteria": [
                "All existing tests pass without modification",
                "No behavioral changes to external interfaces",
                "Code complexity reduced (measurable)",
                "Documentation updated to reflect new structure",
            ],
            "security_considerations": "Ensure refactor does not introduce security regressions. Verify access controls remain intact.",
            "tags": ["refactor", "tech-debt"],
        },
    },
    "security_patch": {
        "name": "Security Patch",
        "slug": "security_patch",
        "description": "Address a security vulnerability or hardening task",
        "defaults": {
            "title": "[SECURITY] ",
            "description": "## Vulnerability Description\n\n## Severity / CVSS Score\n\n## Affected Components\n\n## Remediation Plan\n\n## Verification Method\n",
            "status": "ready",
            "stage": "code",
            "role": "line_worker",
            "priority": 1,
            "acceptance_criteria": [
                "Vulnerability is remediated",
                "Security scan passes clean",
                "No new vulnerabilities introduced",
                "Patch tested against known exploit vectors",
                "Security review completed and approved",
                "Incident documentation updated",
            ],
            "security_considerations": "CRITICAL: This is a security work order. Follow secure development lifecycle. Restrict access to patch details until deployed. Coordinate disclosure timeline.",
            "tags": ["security", "vulnerability", "priority"],
        },
    },
    "infrastructure": {
        "name": "Infrastructure",
        "slug": "infrastructure",
        "description": "Infrastructure, deployment, or operational change",
        "defaults": {
            "title": "[INFRA] ",
            "description": "## Change Description\n\n## Affected Systems\n\n## Rollback Plan\n\n## Monitoring & Alerts\n\n## Dependencies\n",
            "status": "backlog",
            "stage": "operate",
            "role": "line_worker",
            "priority": 3,
            "acceptance_criteria": [
                "Infrastructure change deployed successfully",
                "Monitoring and alerting configured",
                "Rollback plan tested",
                "Documentation updated (runbooks, architecture diagrams)",
                "Performance baseline established",
            ],
            "security_considerations": "Review network exposure, access controls, secrets management, and compliance requirements for infrastructure changes.",
            "tags": ["infrastructure", "operations"],
        },
    },
    "hotfix": {
        "name": "Hotfix",
        "slug": "hotfix",
        "description": "Emergency fix for production issue",
        "defaults": {
            "title": "[HOTFIX] ",
            "description": "## Production Issue\n\n## Impact\n- Users affected: \n- Services affected: \n- Revenue impact: \n\n## Root Cause\n\n## Fix Description\n\n## Rollback Plan\n",
            "status": "in_progress",
            "stage": "code",
            "role": "line_worker",
            "priority": 1,
            "acceptance_criteria": [
                "Production issue resolved",
                "Fix verified in production",
                "Root cause documented",
                "Post-incident review scheduled",
                "Monitoring confirms resolution",
                "Follow-up work order created for permanent fix if needed",
            ],
            "security_considerations": "Hotfix must not bypass security controls. Verify no secrets exposed in logs or error messages. Post-deploy security scan required.",
            "tags": ["hotfix", "production", "urgent"],
        },
    },
}


def get_template(slug):
    return WORK_ORDER_TEMPLATES.get(slug)


def list_templates():
    return [
        {"slug": t["slug"], "name": t["name"], "description": t["description"]}
        for t in WORK_ORDER_TEMPLATES.values()
    ]
