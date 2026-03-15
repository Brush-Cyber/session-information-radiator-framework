import os
import requests

_connection_settings = None


def _get_access_token():
    global _connection_settings

    token = os.environ.get("LINEAR_ACCESS_TOKEN")
    if token:
        return token

    if (_connection_settings
            and _connection_settings.get("settings", {}).get("expires_at")
            and __import__("datetime").datetime.fromisoformat(
                _connection_settings["settings"]["expires_at"].replace("Z", "+00:00")
            ) > __import__("datetime").datetime.now(__import__("datetime").timezone.utc)):
        return _connection_settings["settings"]["access_token"]

    hostname = os.environ.get("REPLIT_CONNECTORS_HOSTNAME")
    repl_identity = os.environ.get("REPL_IDENTITY")
    web_repl_renewal = os.environ.get("WEB_REPL_RENEWAL")

    if repl_identity:
        x_replit_token = "repl " + repl_identity
    elif web_repl_renewal:
        x_replit_token = "depl " + web_repl_renewal
    else:
        raise RuntimeError("No LINEAR_ACCESS_TOKEN or Replit identity token found")

    if not hostname:
        raise RuntimeError("REPLIT_CONNECTORS_HOSTNAME not set")

    resp = requests.get(
        f"https://{hostname}/api/v2/connection?include_secrets=true&connector_names=linear",
        headers={"Accept": "application/json", "X-Replit-Token": x_replit_token},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    item = data.get("items", [None])[0]

    if not item:
        raise RuntimeError("Linear not connected")

    settings = item.get("settings", {})
    access_token = settings.get("access_token") or settings.get("oauth", {}).get("credentials", {}).get("access_token")

    if not access_token:
        raise RuntimeError("Linear access token not found")

    _connection_settings = item
    return access_token


def graphql(query, variables=None):
    token = _get_access_token()
    auth_value = f"Bearer {token}" if not token.startswith("Bearer ") else token
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = requests.post(
        "https://api.linear.app/graphql",
        headers={"Authorization": auth_value, "Content-Type": "application/json"},
        json=payload,
        timeout=15,
    )
    resp.raise_for_status()
    result = resp.json()
    if "errors" in result:
        raise RuntimeError(f"Linear GraphQL error: {result['errors']}")
    return result.get("data", {})


def get_teams():
    data = graphql("{ teams { nodes { id name key } } }")
    return data.get("teams", {}).get("nodes", [])


def get_team_states(team_id):
    data = graphql(
        "query($id: String!) { team(id: $id) { states { nodes { id name type } } } }",
        {"id": team_id},
    )
    return data.get("team", {}).get("states", {}).get("nodes", [])


def get_team_labels(team_id):
    data = graphql(
        "query($id: String!) { team(id: $id) { labels { nodes { id name } } } }",
        {"id": team_id},
    )
    return data.get("team", {}).get("labels", {}).get("nodes", [])


def create_issue(team_id, title, description="", state_id=None, priority=None, label_ids=None, project_id=None):
    mutation = """
    mutation($input: IssueCreateInput!) {
        issueCreate(input: $input) {
            success
            issue { id identifier title url }
        }
    }
    """
    input_data = {"teamId": team_id, "title": title}
    if description:
        input_data["description"] = description
    if state_id:
        input_data["stateId"] = state_id
    if priority is not None:
        input_data["priority"] = priority
    if label_ids:
        input_data["labelIds"] = label_ids
    if project_id:
        input_data["projectId"] = project_id

    data = graphql(mutation, {"input": input_data})
    result = data.get("issueCreate", {})
    if not result.get("success"):
        raise RuntimeError("Failed to create Linear issue")
    return result.get("issue", {})


def update_issue(issue_id, state_id=None, title=None, description=None, priority=None, label_ids=None):
    mutation = """
    mutation($id: String!, $input: IssueUpdateInput!) {
        issueUpdate(id: $id, input: $input) {
            success
            issue { id identifier title url state { name } }
        }
    }
    """
    input_data = {}
    if state_id:
        input_data["stateId"] = state_id
    if title:
        input_data["title"] = title
    if description is not None:
        input_data["description"] = description
    if priority is not None:
        input_data["priority"] = priority
    if label_ids is not None:
        input_data["labelIds"] = label_ids

    if not input_data:
        return None

    data = graphql(mutation, {"id": issue_id, "input": input_data})
    result = data.get("issueUpdate", {})
    if not result.get("success"):
        raise RuntimeError(f"Failed to update Linear issue {issue_id}")
    return result.get("issue")


def get_projects(first=50):
    data = graphql("""
    query($first: Int) {
        projects(first: $first) {
            nodes { id name state }
        }
    }
    """, {"first": first})
    return data.get("projects", {}).get("nodes", [])


def get_issue(issue_id):
    data = graphql(
        """query($id: String!) {
            issue(id: $id) {
                id identifier title description url
                priority updatedAt
                state { id name type }
                labels { nodes { id name } }
            }
        }""",
        {"id": issue_id},
    )
    return data.get("issue")


def get_team_issues(team_id, first=50):
    data = graphql(
        """query($teamId: String!, $first: Int) {
            team(id: $teamId) {
                issues(first: $first, orderBy: updatedAt) {
                    nodes {
                        id identifier title description url
                        priority
                        state { id name type }
                        labels { nodes { id name } }
                    }
                }
            }
        }""",
        {"teamId": team_id, "first": first},
    )
    return data.get("team", {}).get("issues", {}).get("nodes", [])
