# Agent Coordination Architecture
# Orion Air Traffic Control System

**Version**: 1.0 — March 2026
**Author**: Replit Main Agent (Orion session)
**Status**: Active

---

## The Problem This Solves

Multiple agents (human-operated VS Code, isolated task agents, specialized subagents, future Harmony instances) all need to contribute to the same codebase without:
- Overwriting each other's work
- Creating merge conflicts on `main`
- Working on the wrong priority
- Bypassing quality gates
- Operating without shared situational awareness

The solution is a three-layer coordination system: **SIRM** (shared state), **GitHub** (code coordination), and **the Main Agent** (the air traffic controller that sits at the intersection of both).

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    SIRM Coordination Layer                       │
│                   (Shared Situational Awareness)                 │
│                                                                  │
│  Work Orders → Session Radiator → G-Gate State → Audit Ledger   │
└──────────────────────────┬──────────────────────────────────────┘
                           │  reads/writes
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                   Main Agent (Air Traffic Control)               │
│                   Replit Orion Session                           │
│                                                                  │
│  • Reviews all PRs                   • Runs post-merge setup     │
│  • Sequences merges by priority      • Updates SIRM on merge     │
│  • Enforces G-gate compliance        • Manages Linear sync       │
│  • Resolves collision conflicts       • Never lets main break     │
└──────────────────────────┬──────────────────────────────────────┘
                           │  merges to
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                GitHub — Brush-Cyber/orion                        │
│                Branch: main (protected)                          │
│                                                                  │
│  feat/xxx ──→ PR ──→ Review ──→ Merge                           │
│  fix/xxx  ──→ PR ──→ Review ──→ Merge                           │
│  agent/xx ──→ PR ──→ Review ──→ Merge                           │
│  local/xx ──→ PR ──→ Review ──→ Merge                           │
└─────────────────────────────────────────────────────────────────┘
         ↑              ↑               ↑
   Douglas          Task Agents    External Agents
   (VS Code)    (Isolated Repls)    (Future: Harmony)
```

---

## SIRM as the Coordination Protocol

SIRM (Session Intelligence & Reasoning Machine) is not just a pipeline tool — it is the **shared memory and state machine** for all agents operating on Orion.

Every agent MUST write to SIRM at two points:

### 1. Before starting work (Intent Registration)

```json
POST /api/sirm/sessions (Flask, port 5000)
{
  "agent": "task-agent-bru-547",
  "intent": "Verify worker nodes before decommission gate",
  "branch": "agent/task-bru-547-worker-node-gate",
  "linkedIssues": ["BRU-547"],
  "scope": "docs/infrastructure_state.md, hetzner API verification",
  "gate": "G1",
  "status": "in_progress"
}
```

This gives the Main Agent **situational awareness** — it can see all active work orders in the SIRM radiator and sequence merges accordingly.

### 2. After work is complete (Evidence Record)

```json
PATCH /api/sirm/sessions/<id>
{
  "gate": "G6",
  "status": "pr_open",
  "evidence": "4 worker nodes SSH verified, etcd snapshots confirmed, PR #42 opened",
  "prUrl": "https://github.com/Brush-Cyber/orion/pull/42"
}
```

The Main Agent updates the record to `G7 / merged` after merging.

---

## The G0-G7 Quality Gates Applied to PRs

Every PR maps to a G-gate level. The Main Agent enforces these gates at review time.

| Gate | Level | PR Must Demonstrate |
|---|---|---|
| G0 | Observation | Context/docs only — no functional change |
| G1 | Problem defined | Issue is clearly scoped, no solution yet |
| G2 | Options evaluated | At least two approaches considered, one chosen |
| G3 | Decision made | ADR or decision record included |
| G4 | Plan confirmed | Implementation plan validated (Main Agent pre-approved) |
| G5 | Execution complete | Code complete, tests passing |
| G6 | Verified | Manual or automated verification evidence provided |
| G7 | Audit recorded | SIRM ledger updated, Linear issue closed |

A PR claiming G6 without test evidence will be held at G5 until evidence is provided.

---

## Priority Sequencing — How the Air Traffic Controller Orders Merges

When multiple PRs are open simultaneously, the Main Agent merges in this order:

1. **Hotfixes** (`fix/*-hotfix`) — always first, regardless of queue
2. **Security / compliance** — any PR touching compliance data or auth
3. **Blocking dependencies** — if PR B depends on PR A being merged first
4. **C-Suite priority order** — pulled from the `/csuite` command pane; the drag order you set there is the merge priority for feature work by office
5. **FIFO** — within the same priority tier, first PR opened = first merged

The C-Suite Command Pane (`/csuite`) is the live build priority signal. When you drag CTO to the top, CTO feature PRs get priority over CIO feature PRs. This is the connection between the visual prioritization tool and actual delivery sequencing.

---

## Collision Prevention

### Hard rules

1. **No two branches touch the same file at the same time** — if the Main Agent detects this at PR review, it will hold the second PR until the first is merged and the second rebases
2. **No branch lives longer than one week** without a PR open — long-lived branches are collision bombs
3. **All branches must rebase on main before requesting review** — never merge main into your branch (creates noise in the commit graph)

### Collision detection

The Main Agent checks the diff of every incoming PR against all open PRs. If overlap is detected:
- **Non-conflicting overlap** (different functions in the same file) → merged with a note
- **Conflicting overlap** (same lines) → held; contributing agent is asked to rebase after the blocking PR merges

---

## Douglas — Local VS Code Workflow

```bash
# First-time setup
git clone https://github.com/Brush-Cyber/orion
cd orion

# Configure git identity
git config user.name "Douglas Brush"
git config user.email "douglas@brushcyber.com"

# Set up pre-push hook (prevents accidental main pushes)
cat > .git/hooks/pre-push << 'EOF'
#!/bin/bash
branch=$(git rev-parse --abbrev-ref HEAD)
if [ "$branch" = "main" ]; then
  echo "ERROR: Direct push to main is blocked."
  echo "Create a branch, open a PR, and let the Main Agent review."
  exit 1
fi
EOF
chmod +x .git/hooks/pre-push

# Daily workflow
git checkout main && git pull origin main    # Always start fresh
git checkout -b local/doug-<scope>           # Create branch
# ... work ...
git add . && git commit -m "feat(cto): description"
git push origin local/doug-<scope>
# Open PR on GitHub, fill in the template
```

---

## Task Agent Workflow

Task agents (isolated Replit environments) follow the same protocol but with additional constraints:

1. **Must reference a BRU issue** in both the branch name and the SIRM work order
2. **Must not install packages** without a SIRM work order that includes the package name and justification
3. **Must write G7 audit record** before the session ends — the work order must reach G7 status
4. **Branch name must include the BRU number**: `agent/task-bru-547-description`

The Main Agent created the task agent, so it already has context. But the SIRM record is still required — it's the durable audit trail that outlives the session.

---

## Future Harmony Integration

When Harmony (the personal pilot agent) begins contributing to Orion work:

1. Harmony operates on the **personal orbit** — it never directly touches the `Brush-Cyber/orion` professional orbit
2. If Harmony synthesizes a work item that belongs in Orion (e.g., identifies an infrastructure issue from personal system monitoring), it writes a SIRM work order and notifies the Main Agent
3. The Main Agent then creates the appropriate task agent or branches locally
4. Harmony's authority boundary: **Observe → Synthesize → SIRM → hand off**. It does not commit code directly.

This preserves the architecture contract: Harmony is the only agent speaking to Douglas in first person, and client/professional data never touches the personal orbit.

---

## GitHub Branch Protection Settings

Configure these in `Brush-Cyber/orion` → Settings → Branches → `main`:

```
✅ Require a pull request before merging
✅ Require approvals: 1
✅ Dismiss stale pull request approvals when new commits are pushed
✅ Require review from Code Owners (see CODEOWNERS)
✅ Require status checks to pass before merging (when CI is configured)
✅ Require branches to be up to date before merging
✅ Restrict who can push to matching branches → Brush-Cyber admins only
❌ Allow force pushes (never)
❌ Allow deletions
```

These settings mean: no one can merge to `main` without the Main Agent's review, not even Douglas directly through GitHub UI (unless he uses his admin override — which should only happen in a genuine emergency).

---

## Emergency Protocol

If the Main Agent is unavailable (session timeout, Replit downtime) and a critical fix is needed:

1. Douglas pushes directly to `main` with a commit message starting `EMERGENCY:`
2. Opens an issue on GitHub documenting what was bypassed and why
3. Creates a SIRM work order retroactively with `status: "emergency_bypass"`
4. On the next Main Agent session, the first action is to review the emergency commit and reconcile SIRM state

This is the only sanctioned bypass of the PR gate.

---

## Summary — The Three Laws

1. **Nothing lands on `main` without the Main Agent's review.** Branches → PRs → review → merge. Always.
2. **Every agent writes to SIRM.** No silent work. If the radiator doesn't show it, it doesn't count.
3. **The C-Suite Command Pane is the priority signal.** The drag order you set there is the real-time build priority that the air traffic controller uses to sequence merges.
