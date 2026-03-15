from collections import defaultdict
from difflib import SequenceMatcher
from sirm import linear_client
from sirm.models import _now

PRODUCT_LINES = {
    "Core Products": {
        "description": "Revenue-generating applications",
        "projects": [
            "FreeIRPlan", "IRPlan.com", ".builders Suite",
            "RACI Builders", "Pacer Guru", "KIP — Knowledge Intelligence Platform",
        ],
    },
    "Platform & Infrastructure": {
        "description": "Shared services powering products",
        "projects": [
            "Platform Infrastructure", "Infrastructure Reliability",
            "Phase 1: Foundation", "Phase 2: Delivery", "Phase 4: Hardening",
            "CI/CD Pipeline Hardening", "Orion Migration", "Orion's Belt",
        ],
    },
    "Strategy & Governance": {
        "description": "Factory-level planning",
        "projects": [
            "Brush Cyber — Product Roadmap", "Brush Cyber — Style Guide",
            "Revenue Engine", "Billing Modules v2", "Forge",
        ],
    },
}

TEAM_ID = "0c75b8b9-357f-442b-a15a-66ad185306a6"

FACTORY_LABEL_PREFIXES = ["sirm/", "phase/", "roadmap/"]

DONE_STATE_TYPES = {"completed", "done", "canceled", "cancelled"}
ACTIVE_STATE_TYPES = {"started", "in progress", "unstarted", "triage", "backlog", "todo"}


def _fetch_all_projects():
    data = linear_client.graphql("""
    {
        projects(first: 50) {
            nodes {
                id
                name
                state
                progress
                startDate
                targetDate
                updatedAt
            }
        }
    }
    """)
    projects = data.get("projects", {}).get("nodes", [])

    for proj in projects:
        try:
            issues_data = linear_client.graphql("""
            query($projectId: String!) {
                project(id: $projectId) {
                    issues(first: 250) {
                        nodes {
                            id
                            identifier
                            title
                            url
                            priority
                            updatedAt
                            state { id name type }
                            labels { nodes { id name } }
                            project { id name }
                        }
                    }
                }
            }
            """, {"projectId": proj["id"]})
            proj["issues"] = issues_data.get("project", {}).get("issues", {})
        except Exception:
            proj["issues"] = {"nodes": []}

    return projects


def _fetch_team_issues(team_id=TEAM_ID, limit=250):
    data = linear_client.graphql("""
    query($teamId: String!, $first: Int) {
        team(id: $teamId) {
            issues(first: $first, orderBy: updatedAt) {
                nodes {
                    id
                    identifier
                    title
                    url
                    priority
                    updatedAt
                    state { id name type }
                    labels { nodes { id name } }
                    project { id name }
                }
            }
        }
    }
    """, {"teamId": team_id, "first": limit})
    return data.get("team", {}).get("issues", {}).get("nodes", [])


def _classify_project(project_name):
    for line_name, line_info in PRODUCT_LINES.items():
        for known in line_info["projects"]:
            if known.lower() in project_name.lower() or project_name.lower() in known.lower():
                return line_name
    return "Unclassified"


def _is_done(issue):
    state_type = (issue.get("state") or {}).get("type", "").lower()
    state_name = (issue.get("state") or {}).get("name", "").lower()
    return state_type in DONE_STATE_TYPES or state_name in DONE_STATE_TYPES


def _is_blocked(issue):
    state_name = (issue.get("state") or {}).get("name", "").lower()
    labels = [l["name"].lower() for l in (issue.get("labels") or {}).get("nodes", [])]
    return "blocked" in state_name or "blocked" in labels


def _get_label_names(issue):
    return [l["name"] for l in (issue.get("labels") or {}).get("nodes", [])]


def _is_factory_label(label_name):
    lower = label_name.lower()
    return any(lower.startswith(prefix) for prefix in FACTORY_LABEL_PREFIXES)


def _similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def get_orchestration_data():
    try:
        projects = _fetch_all_projects()
    except Exception:
        projects = []

    try:
        all_issues = _fetch_team_issues()
    except Exception:
        all_issues = []

    project_map = {}
    for proj in projects:
        proj_issues = (proj.get("issues") or {}).get("nodes", [])
        project_map[proj["name"]] = {
            "id": proj["id"],
            "name": proj["name"],
            "state": proj.get("state", ""),
            "progress": proj.get("progress", 0),
            "start_date": proj.get("startDate", ""),
            "target_date": proj.get("targetDate", ""),
            "updated_at": proj.get("updatedAt", ""),
            "issues": proj_issues,
            "product_line": _classify_project(proj["name"]),
        }

    issue_by_project = defaultdict(list)
    for issue in all_issues:
        proj = issue.get("project")
        proj_name = proj["name"] if proj else "No Project"
        issue_by_project[proj_name].append(issue)

    for proj_name, issues in issue_by_project.items():
        if proj_name not in project_map:
            project_map[proj_name] = {
                "id": None,
                "name": proj_name,
                "state": "",
                "progress": 0,
                "start_date": "",
                "target_date": "",
                "updated_at": "",
                "issues": issues,
                "product_line": _classify_project(proj_name),
            }
        else:
            existing_ids = {i["id"] for i in project_map[proj_name]["issues"]}
            for issue in issues:
                if issue["id"] not in existing_ids:
                    project_map[proj_name]["issues"].append(issue)

    all_combined_issues = []
    for proj_data in project_map.values():
        all_combined_issues.extend(proj_data["issues"])

    seen_ids = set()
    unique_issues = []
    for issue in all_combined_issues:
        if issue["id"] not in seen_ids:
            seen_ids.add(issue["id"])
            unique_issues.append(issue)
    all_combined_issues = unique_issues

    total_issues = len(all_combined_issues)
    done_issues = [i for i in all_combined_issues if _is_done(i)]
    active_issues = [i for i in all_combined_issues if not _is_done(i)]
    blocked_issues = [i for i in all_combined_issues if _is_blocked(i)]

    product_line_data = {}
    for line_name, line_info in PRODUCT_LINES.items():
        line_projects = []
        line_total = 0
        line_done = 0
        line_active = 0
        line_blocked = 0
        for proj_name, proj_data in project_map.items():
            if proj_data["product_line"] == line_name:
                p_issues = proj_data["issues"]
                p_done = len([i for i in p_issues if _is_done(i)])
                p_active = len([i for i in p_issues if not _is_done(i)])
                p_blocked = len([i for i in p_issues if _is_blocked(i)])
                line_projects.append({
                    "name": proj_name,
                    "total": len(p_issues),
                    "done": p_done,
                    "active": p_active,
                    "blocked": p_blocked,
                    "progress": round((p_done / len(p_issues)) * 100) if p_issues else 0,
                    "updated_at": proj_data.get("updated_at", ""),
                })
                line_total += len(p_issues)
                line_done += p_done
                line_active += p_active
                line_blocked += p_blocked
        product_line_data[line_name] = {
            "description": line_info["description"],
            "projects": sorted(line_projects, key=lambda p: p["total"], reverse=True),
            "total_issues": line_total,
            "done": line_done,
            "active": line_active,
            "blocked": line_blocked,
            "progress": round((line_done / line_total) * 100) if line_total else 0,
        }

    label_distribution: dict[str, dict] = {}
    for issue in all_combined_issues:
        proj = issue.get("project")
        proj_name = proj["name"] if proj else "No Project"
        for label in _get_label_names(issue):
            if label not in label_distribution:
                label_distribution[label] = {"count": 0, "projects": set()}
            label_distribution[label]["count"] += 1
            label_distribution[label]["projects"].add(proj_name)

    factory_labels = {}
    for label, info in label_distribution.items():
        if _is_factory_label(label):
            factory_labels[label] = {
                "count": info["count"],
                "projects": sorted(info["projects"]),
                "cross_product": len(info["projects"]) > 1,
            }

    cross_product_labels = {}
    for label, info in label_distribution.items():
        if len(info["projects"]) > 1:
            cross_product_labels[label] = {
                "count": info["count"],
                "projects": sorted(info["projects"]),
            }

    shared_blockers = []
    blocker_by_label = defaultdict(list)
    for issue in blocked_issues:
        for label in _get_label_names(issue):
            blocker_by_label[label].append(issue)
    for label, issues in blocker_by_label.items():
        projects_affected = set()
        for i in issues:
            proj = i.get("project")
            if proj:
                projects_affected.add(proj["name"])
        if len(projects_affected) > 1:
            shared_blockers.append({
                "label": label,
                "issues": [{
                    "id": i["id"],
                    "identifier": i.get("identifier", ""),
                    "title": i["title"],
                    "project": (i.get("project") or {}).get("name", ""),
                    "url": i.get("url", ""),
                } for i in issues],
                "projects_affected": sorted(projects_affected),
            })

    factory_decisions = []
    for label, info in factory_labels.items():
        if info["cross_product"]:
            related = []
            for issue in all_combined_issues:
                if label in _get_label_names(issue):
                    related.append({
                        "id": issue["id"],
                        "identifier": issue.get("identifier", ""),
                        "title": issue["title"],
                        "project": (issue.get("project") or {}).get("name", ""),
                        "state": (issue.get("state") or {}).get("name", ""),
                        "url": issue.get("url", ""),
                    })
            factory_decisions.append({
                "label": label,
                "projects": info["projects"],
                "issue_count": info["count"],
                "issues": related[:20],
            })

    duplicates = []
    issue_titles = [(i.get("identifier", ""), i["title"], (i.get("project") or {}).get("name", "")) for i in all_combined_issues if not _is_done(i)]
    checked = set()
    for idx, (id_a, title_a, proj_a) in enumerate(issue_titles):
        for jdx, (id_b, title_b, proj_b) in enumerate(issue_titles[idx + 1:], start=idx + 1):
            if proj_a == proj_b:
                continue
            pair_key = tuple(sorted([id_a, id_b]))
            if pair_key in checked:
                continue
            checked.add(pair_key)
            sim = _similarity(title_a, title_b)
            if sim >= 0.7:
                duplicates.append({
                    "similarity": round(sim * 100),
                    "issue_a": {"identifier": id_a, "title": title_a, "project": proj_a},
                    "issue_b": {"identifier": id_b, "title": title_b, "project": proj_b},
                })
    duplicates.sort(key=lambda d: d["similarity"], reverse=True)
    duplicates = duplicates[:25]

    project_matrix = []
    for proj_name, proj_data in sorted(project_map.items()):
        p_issues = proj_data["issues"]
        p_done = len([i for i in p_issues if _is_done(i)])
        p_active = len([i for i in p_issues if not _is_done(i)])
        p_blocked = len([i for i in p_issues if _is_blocked(i)])
        project_matrix.append({
            "name": proj_name,
            "product_line": proj_data["product_line"],
            "total": len(p_issues),
            "active": p_active,
            "done": p_done,
            "blocked": p_blocked,
            "progress": round((p_done / len(p_issues)) * 100) if p_issues else 0,
            "updated_at": proj_data.get("updated_at", ""),
            "state": proj_data.get("state", ""),
        })

    infra_projects = [p for p in project_matrix if p["product_line"] == "Platform & Infrastructure"]
    infra_total = sum(p["total"] for p in infra_projects)
    infra_done = sum(p["done"] for p in infra_projects)
    infra_progress = round((infra_done / infra_total) * 100) if infra_total else 0

    shared_labels_count = len(cross_product_labels)
    governance_projects = [p for p in project_matrix if p["product_line"] == "Strategy & Governance"]
    governance_done = sum(p["done"] for p in governance_projects)
    governance_total = sum(p["total"] for p in governance_projects)
    governance_progress = round((governance_done / governance_total) * 100) if governance_total else 0

    readiness_checks = [
        {"name": "Shared infrastructure defined", "passed": len(infra_projects) >= 3, "detail": f"{len(infra_projects)} infra projects exist"},
        {"name": "Infrastructure >50% complete", "passed": infra_progress > 50, "detail": f"{infra_progress}% complete"},
        {"name": "Cross-product labels established", "passed": shared_labels_count >= 3, "detail": f"{shared_labels_count} shared labels"},
        {"name": "CI/CD pipeline exists", "passed": any("ci/cd" in p["name"].lower() for p in project_matrix), "detail": "CI/CD project found" if any("ci/cd" in p["name"].lower() for p in project_matrix) else "No CI/CD project"},
        {"name": "Style guide established", "passed": any("style" in p["name"].lower() for p in project_matrix), "detail": "Style guide project found" if any("style" in p["name"].lower() for p in project_matrix) else "No style guide"},
        {"name": "Governance framework >30% complete", "passed": governance_progress > 30, "detail": f"{governance_progress}% governance complete"},
        {"name": "No critical shared blockers", "passed": len(shared_blockers) == 0, "detail": f"{len(shared_blockers)} shared blockers"},
    ]
    readiness_score = round((sum(1 for c in readiness_checks if c["passed"]) / len(readiness_checks)) * 100)

    overall_progress = round((len(done_issues) / total_issues) * 100) if total_issues else 0
    blocker_ratio = round((len(blocked_issues) / total_issues) * 100) if total_issues else 0
    velocity_indicator = "healthy" if blocker_ratio < 15 and overall_progress > 20 else "at_risk" if blocker_ratio < 30 else "critical"

    health_score = max(0, min(100, round(
        (overall_progress * 0.3) +
        ((100 - blocker_ratio) * 0.3) +
        (readiness_score * 0.2) +
        (min(len(project_matrix) * 5, 100) * 0.2)
    )))

    for line_name, line_data in product_line_data.items():
        for proj in line_data["projects"]:
            for pn, pd in project_map.items():
                if pn == proj["name"] and pd.get("id"):
                    proj["id"] = pd["id"]
                    break

    for proj_entry in project_matrix:
        for pn, pd in project_map.items():
            if pn == proj_entry["name"] and pd.get("id"):
                proj_entry["id"] = pd["id"]
                break

    return {
        "fetched_at": _now(),
        "overview": {
            "total_projects": len(project_map),
            "total_issues": total_issues,
            "active_issues": len(active_issues),
            "done_issues": len(done_issues),
            "blocked_issues": len(blocked_issues),
            "overall_progress": overall_progress,
            "blocker_ratio": blocker_ratio,
            "health_score": health_score,
            "velocity_indicator": velocity_indicator,
        },
        "product_lines": product_line_data,
        "project_matrix": project_matrix,
        "cross_product_insights": {
            "shared_blockers": shared_blockers,
            "factory_decisions": factory_decisions,
            "duplicates": duplicates,
            "cross_product_labels": cross_product_labels,
            "factory_labels": factory_labels,
        },
        "new_product_readiness": {
            "score": readiness_score,
            "checks": readiness_checks,
            "infra_progress": infra_progress,
            "governance_progress": governance_progress,
        },
    }


def _fetch_project_detail(project_id):
    data = linear_client.graphql("""
    query($projectId: String!) {
        project(id: $projectId) {
            id
            name
            description
            state
            progress
            startDate
            targetDate
            updatedAt
            issues(first: 250) {
                nodes {
                    id
                    identifier
                    title
                    url
                    priority
                    updatedAt
                    createdAt
                    state { id name type }
                    labels { nodes { id name } }
                    assignee { id name displayName email }
                    project { id name }
                }
            }
        }
    }
    """, {"projectId": project_id})
    return data.get("project", {})


def _classify_issue_state(issue):
    state = issue.get("state") or {}
    state_type = state.get("type", "").lower()
    state_name = state.get("name", "").lower()
    if state_type in {"completed", "done"} or state_name in {"done", "completed"}:
        return "done"
    if state_type in {"canceled", "cancelled"} or state_name in {"canceled", "cancelled"}:
        return "cancelled"
    if state_type == "started" or state_name in {"in progress", "in_progress"}:
        return "in_progress"
    if state_name == "todo" or state_type == "unstarted":
        return "todo"
    return "backlog"


PRIORITY_LABELS = {0: "No priority", 1: "Urgent", 2: "High", 3: "Medium", 4: "Low"}


def get_project_detail(project_id):
    try:
        project = _fetch_project_detail(project_id)
    except Exception:
        return None

    if not project or not project.get("id"):
        return None

    issues = (project.get("issues") or {}).get("nodes", [])
    product_line = _classify_project(project.get("name", ""))

    state_breakdown = {"backlog": [], "todo": [], "in_progress": [], "done": [], "cancelled": []}
    priority_breakdown = {0: [], 1: [], 2: [], 3: [], 4: []}
    label_counts = defaultdict(int)
    all_labels = set()

    for issue in issues:
        bucket = _classify_issue_state(issue)
        state_breakdown[bucket].append(issue)

        pri = issue.get("priority", 0) or 0
        if pri in priority_breakdown:
            priority_breakdown[pri].append(issue)

        for label in _get_label_names(issue):
            label_counts[label] += 1
            all_labels.add(label)

    total = len(issues)
    done_count = len(state_breakdown["done"])
    cancelled_count = len(state_breakdown["cancelled"])
    active_count = len(state_breakdown["in_progress"])
    blocked_count = len([i for i in issues if _is_blocked(i)])

    blocker_ratio = round((blocked_count / total) * 100) if total else 0
    completion = round((done_count / total) * 100) if total else 0
    health_score = max(0, min(100, round(
        (completion * 0.4) +
        ((100 - blocker_ratio) * 0.3) +
        (min(active_count * 10, 100) * 0.15) +
        (min(total, 100) * 0.15)
    )))

    top_blockers = []
    for issue in issues:
        if _is_blocked(issue):
            top_blockers.append({
                "id": issue["id"],
                "identifier": issue.get("identifier", ""),
                "title": issue["title"],
                "url": issue.get("url", ""),
                "priority": issue.get("priority", 0),
                "labels": _get_label_names(issue),
                "assignee": (issue.get("assignee") or {}).get("displayName", ""),
            })
    top_blockers.sort(key=lambda x: x.get("priority", 4))

    recent_activity = sorted(issues, key=lambda i: i.get("updatedAt", ""), reverse=True)[:10]
    recent_activity_formatted = []
    for issue in recent_activity:
        recent_activity_formatted.append({
            "id": issue["id"],
            "identifier": issue.get("identifier", ""),
            "title": issue["title"],
            "url": issue.get("url", ""),
            "state": (issue.get("state") or {}).get("name", ""),
            "priority": issue.get("priority", 0),
            "updated_at": issue.get("updatedAt", ""),
            "assignee": (issue.get("assignee") or {}).get("displayName", ""),
        })

    try:
        all_projects = _fetch_all_projects()
    except Exception:
        all_projects = []

    project_labels = all_labels
    crosswalks = []
    for other_proj in all_projects:
        if other_proj["id"] == project_id:
            continue
        other_issues = (other_proj.get("issues") or {}).get("nodes", [])
        other_labels = set()
        for oi in other_issues:
            for label in _get_label_names(oi):
                other_labels.add(label)

        shared = project_labels & other_labels
        if shared:
            shared_issues = []
            for oi in other_issues:
                oi_labels = set(_get_label_names(oi))
                if oi_labels & shared:
                    shared_issues.append({
                        "id": oi["id"],
                        "identifier": oi.get("identifier", ""),
                        "title": oi["title"],
                        "url": oi.get("url", ""),
                        "state": (oi.get("state") or {}).get("name", ""),
                    })
            crosswalks.append({
                "project_id": other_proj["id"],
                "project_name": other_proj["name"],
                "shared_labels": sorted(shared),
                "shared_label_count": len(shared),
                "related_issues": shared_issues[:20],
                "related_issue_count": len(shared_issues),
            })
    crosswalks.sort(key=lambda c: c["shared_label_count"], reverse=True)

    issue_list = []
    for issue in issues:
        issue_list.append({
            "id": issue["id"],
            "identifier": issue.get("identifier", ""),
            "title": issue["title"],
            "url": issue.get("url", ""),
            "state": (issue.get("state") or {}).get("name", ""),
            "state_type": (issue.get("state") or {}).get("type", ""),
            "state_bucket": _classify_issue_state(issue),
            "priority": issue.get("priority", 0),
            "priority_label": PRIORITY_LABELS.get(issue.get("priority", 0), "Unknown"),
            "labels": _get_label_names(issue),
            "assignee": (issue.get("assignee") or {}).get("displayName", ""),
            "updated_at": issue.get("updatedAt", ""),
            "created_at": issue.get("createdAt", ""),
        })

    label_cloud = [{"name": label, "count": count} for label, count in sorted(label_counts.items(), key=lambda x: x[1], reverse=True)]

    priority_distribution = []
    for pri in range(5):
        priority_distribution.append({
            "priority": pri,
            "label": PRIORITY_LABELS.get(pri, "Unknown"),
            "count": len(priority_breakdown.get(pri, [])),
        })

    return {
        "fetched_at": _now(),
        "project": {
            "id": project.get("id", ""),
            "name": project.get("name", ""),
            "description": project.get("description", ""),
            "state": project.get("state", ""),
            "progress": project.get("progress", 0),
            "start_date": project.get("startDate", ""),
            "target_date": project.get("targetDate", ""),
            "updated_at": project.get("updatedAt", ""),
            "product_line": product_line,
        },
        "health": {
            "score": health_score,
            "total": total,
            "done": done_count,
            "active": active_count,
            "blocked": blocked_count,
            "cancelled": cancelled_count,
            "completion_pct": completion,
            "blocker_ratio": blocker_ratio,
        },
        "state_breakdown": {
            bucket: len(items) for bucket, items in state_breakdown.items()
        },
        "priority_distribution": priority_distribution,
        "issues": issue_list,
        "crosswalks": crosswalks,
        "top_blockers": top_blockers,
        "recent_activity": recent_activity_formatted,
        "label_cloud": label_cloud,
    }


def get_crosswalk_map():
    try:
        projects = _fetch_all_projects()
    except Exception:
        return {"projects": [], "edges": [], "matrix": []}

    project_label_map = {}
    for proj in projects:
        proj_issues = (proj.get("issues") or {}).get("nodes", [])
        labels = set()
        for issue in proj_issues:
            for label in _get_label_names(issue):
                labels.add(label)
        project_label_map[proj["id"]] = {
            "id": proj["id"],
            "name": proj["name"],
            "labels": labels,
            "issue_count": len(proj_issues),
        }

    project_ids = sorted(project_label_map.keys(), key=lambda pid: project_label_map[pid]["name"])
    project_list = [{"id": pid, "name": project_label_map[pid]["name"]} for pid in project_ids]

    edges = []
    matrix = []

    for i, pid_a in enumerate(project_ids):
        row = []
        for j, pid_b in enumerate(project_ids):
            if i == j:
                row.append(0)
                continue
            shared = project_label_map[pid_a]["labels"] & project_label_map[pid_b]["labels"]
            weight = len(shared)
            row.append(weight)
            if i < j and weight > 0:
                edges.append({
                    "source": pid_a,
                    "source_name": project_label_map[pid_a]["name"],
                    "target": pid_b,
                    "target_name": project_label_map[pid_b]["name"],
                    "weight": weight,
                    "shared_labels": sorted(shared),
                })
        matrix.append(row)

    edges.sort(key=lambda e: e["weight"], reverse=True)

    return {
        "fetched_at": _now(),
        "projects": project_list,
        "edges": edges,
        "matrix": matrix,
    }
