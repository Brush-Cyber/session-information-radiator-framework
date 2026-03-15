# Brush Cyber — New Product Bootstrap Template

Use this template when spinning up any new Brush Cyber product in a fresh Replit project. Copy, fill in the product-specific sections, and hand it to the agent as the first prompt.

---

## CRITICAL: What You Are Building

You are building a **STANDALONE WEB APPLICATION**. This is a complete product that end users visit in their browser and use directly. It has its own domain, its own UI, its own pages, its own database.

**You must build:**
- A full frontend with pages, navigation, and interactive UI
- Server-rendered HTML or a proper SPA framework
- Responsive, polished design using the Brush Cyber design system
- A complete user experience, not just API endpoints

**This is NOT:**
- An API-only backend (if you build only API routes with no frontend, you have failed)
- A module or blade inside Orion (Orion manages this product, it does not host it)
- A microservice or integration layer

**Orion's role:** Orion is the factory. It produces and manages products through the SIRM pipeline (work orders, quality gates, sprint tracking). But each product runs independently at its own domain with its own UI. Orion does not absorb products.

---

## Step 0: Linear Integration — DO THIS FIRST

Every Brush Cyber product connects to Linear for project management from day one. This is NOT optional.

### Setup Instructions

1. **Connect Linear integration**: Use Replit's integration system to add the Linear connector. Search for "Linear" in integrations, add the connection, and propose it to the user if OAuth hasn't been completed.

2. **Create a Linear project** named **"[PRODUCT NAME]"** in the **BRU** team (team key: `BRU`).

3. **Create bootstrap issues** in the new Linear project. Break the product into work items covering:
   - Backend: core API / business logic
   - Frontend: layout + design system implementation
   - Frontend: each major page/view
   - Database: schema setup
   - Deploy: autoscale config + DNS

4. **Move issues to Done** as you complete each piece. Do not leave stale states.

### Linear GraphQL Client (Python)

Include this module in your project. It handles Replit connector auth automatically:

```python
"""Linear GraphQL client — uses Replit Connectors for auth."""
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
        raise RuntimeError("Linear not connected — add the Linear integration in Replit")

    settings = item.get("settings", {})
    access_token = settings.get("access_token") or settings.get("oauth", {}).get("credentials", {}).get("access_token")

    if not access_token:
        raise RuntimeError("Linear access token not found in connector settings")

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


def create_issue(team_id, title, description="", state_id=None, priority=None, project_id=None):
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
    if project_id:
        input_data["projectId"] = project_id

    data = graphql(mutation, {"input": input_data})
    result = data.get("issueCreate", {})
    if not result.get("success"):
        raise RuntimeError("Failed to create Linear issue")
    return result.get("issue", {})


def update_issue(issue_id, state_id=None, title=None, description=None, priority=None):
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

    if not input_data:
        return None

    data = graphql(mutation, {"id": issue_id, "input": input_data})
    result = data.get("issueUpdate", {})
    if not result.get("success"):
        raise RuntimeError(f"Failed to update Linear issue {issue_id}")
    return result.get("issue")
```

### Linear Status Page

Add a `/linear` page to your web UI showing connection status, project name, and issue count.

---

## Step 1: Brush Cyber Design System — TWO TRACKS

Brush Cyber has **two design tracks**. You MUST use the correct one:

### Track A: Client-Facing Products (DEFAULT for new products)

Use for: Arcturus/.builders suite, FreeIR Plan, RACI Builder, Pacer Guru, Identity Recon, Strike Forge, any product a client, law firm, or enterprise buyer will see.

**This is a LIGHT, CLEAN, PROFESSIONAL theme.** White backgrounds, dark text, brand accents. Think: trusted SaaS that a law firm partner or CISO would use. NOT a hacker terminal.

```css
:root {
    /* Brush Cyber brand colors — shared across ALL products */
    --bc-indigo: #413BBE;
    --bc-navy: #211A37;
    --bc-magenta: #D447B2;
    --bc-sky: #47B6EE;
    --bc-crimson: #DB0A38;

    /* CLIENT-FACING LIGHT THEME */
    --bg-primary: #FFFFFF;
    --bg-secondary: #F8F9FC;
    --bg-tertiary: #F0F1F5;
    --bg-card: #FFFFFF;
    --bg-hover: #F0F1F5;
    --bg-hero: linear-gradient(135deg, #1E1A3A 0%, #2D2660 50%, #413BBE 100%);

    --border: #E2E4EA;
    --border-light: #ECEDF2;

    --text-primary: #1A1A2E;
    --text-secondary: #4A4A68;
    --text-muted: #8888A0;
    --text-on-dark: #F4F3F8;

    --accent-blue: var(--bc-indigo);
    --accent-green: #059669;
    --accent-yellow: #D97706;
    --accent-red: var(--bc-crimson);
    --accent-purple: #7C3AED;
    --accent-orange: #EA580C;

    --font-mono: 'JetBrains Mono', 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
    --font-heading: 'Montserrat', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    --font-sans: 'Poppins', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
}
```

**Component patterns:**
- **Cards**: white background, `border: 1px solid var(--border)`, `border-radius: 12px`, `box-shadow: 0 1px 3px rgba(0,0,0,0.06)`
- **Tables**: light gray header (`--bg-tertiary`), white rows, subtle hover
- **Buttons (primary)**: `background: var(--bc-indigo)`, white text, subtle shadow
- **Buttons (secondary)**: white background, border, dark text
- **Inputs**: white background, subtle border, focus border `var(--bc-indigo)`
- **Badges**: light indigo background `rgba(65,59,190,0.08)`, indigo text
- **Navbar**: white background, bottom border, product name in indigo (`--bc-indigo`), Montserrat weight 800
- **Hero** (landing pages only): dark gradient (`--bg-hero`), white text — the ONE place dark backgrounds are used
- **Footer**: light gray (`--bg-secondary`), "A Brush Cyber product"

### Track B: Internal Tools (Orion only)

Use for: Orion management plane, SIRM, KIP — internal dashboards Douglas and agents use. NOT for anything a client sees.

Dark purple-black theme: `--bg-primary: #0D0A14`, `--bg-secondary: #15112A`, light text on dark. Sidebar navigation. Magenta accents.

**If you are building a client-facing product, do NOT use Track B. It is documented here only so you know what NOT to do.**

### Shared Across Both Tracks

- **Google Fonts**: Montserrat (headings), Poppins (body), JetBrains Mono (code) — same weights, same `<link>` tag
- **Brand colors**: `--bc-indigo`, `--bc-navy`, `--bc-magenta`, `--bc-sky`, `--bc-crimson` are the same everywhere
- **Typography rules**: headings = Montserrat 700-800, body = Poppins 300-600, code = JetBrains Mono
- **Border radius**: 8px for buttons/inputs, 12px for cards
- **Layout**: Client-facing = top navbar. Internal = sidebar.

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&family=Poppins:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
```

---

## Step 2: Product-Specific Setup

[Fill in: language, framework, packages, port, database schema, API routes, business logic]

---

## Step 3: Deployment

[Fill in: deployment target, custom domain, DNS zone ID if Cloudflare-managed]

---

## Execution Order

1. **Step 0**: Connect Linear, create project, create bootstrap issues
2. **Step 1**: Apply correct design track (client-facing = light theme)
3. **Step 2**: Build product (backend + frontend) — mark Linear issues Done as you go
4. **Step 3**: Deploy and configure DNS
5. **Verify**: All Linear issues Done, design matches correct track, all pages functional

---

## Product Context

- **Owner**: Douglas Brush (Brush Cyber)
- **Tracked in**: Orion SIRM work order `[WORK_ORDER_ID]`
- **Parent project**: Orion (Brush Cyber Unified Management Plane)
- **Linear team**: BRU
