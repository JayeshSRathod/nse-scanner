# Sprint 15 — Autonomous Investment Intelligence

## Objective

Complete the Market Intelligence Suite roadmap with a governed autonomous decision-cycle foundation. The module may assemble evidence-backed recommendations and track approvals and outcomes, but it must not bypass deterministic controls or human authorization.

## Architecture

```text
Evidence Registry
      ↓
Company / Market / Opportunity / Portfolio Intelligence
      ↓
Decision Intelligence
      ↓
Autonomous Decision Cycle
      ↓
Human Approval Gate
      ↓
Controlled Execution Adapter (future)
      ↓
Immutable Audit Outcome
```

## Implemented contracts

- `AutonomousDecisionCycle`
- `HumanApproval`
- `AutonomousDecisionOutcome`
- controlled scopes, statuses, actions and outcomes
- bounded deterministic score validation
- mandatory evidence for actionable cycles
- mandatory limitations for unresolved cycles
- explicit human approval reference
- execution audit requirements
- expiry-date validation

## Safety invariants

1. No AI-created evidence, score, price or portfolio weight.
2. Insufficient or conflicting evidence cannot produce a portfolio-changing proposal.
3. An approved portfolio-changing proposal requires explicit constraints.
4. Execution requires a human approval reference.
5. Executed outcomes require immutable audit references.
6. Non-executed outcomes must record `NO_ACTION`.
7. No broker or trading API is connected in this sprint.

## Validation

```bash
python -m pytest tests/test_autonomous_investment_intelligence_models.py -q
```

## Roadmap completion

This sprint completes the planned MIS sequence:

1. Technical Scanner
2. Portfolio Intelligence
3. Company Intelligence
4. Market Intelligence
5. Opportunity Intelligence
6. AI Research Assistant
7. Decision Intelligence
8. Autonomous Investment Intelligence

Further work should be treated as production hardening rather than a new roadmap sprint: persistence, orchestration, observability, security review, execution-adapter simulation, approval UI and end-to-end integration tests.
