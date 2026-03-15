# SIRM — G0-G7 Gate Architecture
### The Reasoning Model as Quality Gate System

---

## The Connection

The G0-G7 reasoning model is Doug's cognitive DNA — the sequence his mind runs when evaluating any decision. It was formalized as Harmony's operating framework.

It is also, deliberately, the gate model for SIRM.

SIRM is not just a CI/CD pipeline. It is the product lifecycle expression of the same reasoning sequence that runs the personal intelligence system. Arcturus eats its own cooking: the platform itself ships through the six stages. Every product built in Orion passes through G0-G7 before it reaches members.

---

## The Gate Mapping

| G-Gate | Cognitive Function | SIRM Stage | Gate Question |
|---|---|---|---|
| **G0** | Threat/context check | **Plan** | Is this safe to build? Is there a clear requirement? Is the threat model understood? |
| **G1** | Problem decomposition | **Code** | Is what's being built clearly decomposed? Are acceptance criteria written? |
| **G2** | Data sufficiency | **Build** | Does the build have what it needs? Are dependencies met? Are tests written? |
| **G3** | Hypothesis generation | **Integrate** | Have alternatives been considered? Are integration tests passing? Is the code reviewed? |
| **G4** | Bayesian weighting | **Release** | What is the confidence level this ships cleanly? Are rollback procedures ready? |
| **G5** | Red team | **Operate** | What breaks this in production? Is monitoring live? Has adversarial testing run? |
| **G6** | Decision + commit | **Ship** | Explicit go/no-go with stated confidence. No silent releases. |
| **G7** | Audit | **Ledger** | Log the full reasoning chain. What was decided, why, with what confidence. **Never skip.** |

---

## Directives

- Every release through SIRM runs the full G0-G7 sequence. No shortcuts.
- Every gate override (skipping or force-passing a gate) is logged at G7 with reason and approver.
- G7 is not optional. The audit ledger is the source of truth for what shipped, when, why, and with what confidence.
- The six SIRM stages (Plan → Code → Build → Integrate → Release → Operate) map directly to G0-G5. G6 is the explicit ship decision. G7 is the permanent record.
- SIRM governs how Arcturus itself is built. The gym runs on the same gate system it sells.

---

## Quality Gate Criteria (per stage)

### G0 — Plan Gate
- [ ] Linear issue exists and is accepted into sprint
- [ ] Threat model reviewed (does this touch sensitive data, auth, client data?)
- [ ] Acceptance criteria written
- [ ] Dependencies identified
- [ ] Architecture contract review (does this cross an orbit boundary?)

### G1 — Code Gate
- [ ] Problem fully decomposed into subtasks
- [ ] No orphaned code paths (everything built has a test path)
- [ ] No silent external dependencies introduced
- [ ] PR opened with description referencing Linear issue

### G2 — Build Gate
- [ ] All tests written (unit + integration minimum)
- [ ] Build passes clean (no warnings treated as errors)
- [ ] Migrations tested against current schema
- [ ] No hardcoded credentials, no hardcoded foreign keys

### G3 — Integrate Gate
- [ ] Integration tests passing
- [ ] Code reviewed by at least one agent or human
- [ ] Alternative approaches documented (even if not chosen)
- [ ] No regressions in adjacent modules

### G4 — Release Gate
- [ ] Confidence level stated (e.g., "G4 confidence: 85% — known risk: migration timing")
- [ ] Rollback procedure documented
- [ ] Monitoring / alerting confirmed live for this feature
- [ ] Changelog entry written

### G5 — Operate Gate
- [ ] Adversarial/red team check completed (what breaks this?)
- [ ] Load/edge case testing completed
- [ ] For Arcturus: client data isolation verified
- [ ] For Arcturus: chain of custody verified (Strike Forge, Apex outputs)

### G6 — Ship Decision
- Explicit go/no-go logged with confidence level
- Any open risks stated
- Approver recorded

### G7 — Audit Ledger
- Full G0-G5 gate results recorded
- G6 decision recorded
- Timestamp, version, Linear issue reference
- Any gate overrides with justification
- **This record is immutable.**

---

## Architecture Contracts SIRM Enforces

1. No feature ships without a G7 audit record.
2. Client data is sovereign. Any feature touching Arcturus client data runs a G0 architecture contract review.
3. Apex completion data automatically feeds compliance modules — SIRM validates this wiring on every Apex release.
4. WISP and FreeIR share a single policy layer. SIRM prevents any release that creates a second policy data model.
5. Three60 plugin integrations are additive. SIRM gates block any release where core Arcturus functionality depends on a plugin being active.

---

*Last updated: 2026-03-15 | Source: Vision Package v3.0 + Agent Directives*
