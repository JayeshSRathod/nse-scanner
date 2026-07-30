# Sprint 15 — Autonomous Investment Intelligence

## Objective

Introduce a controlled orchestration layer that can schedule observation, research, review, and alert tasks using verified MIS evidence.

## Initial scope

- Evidence-bound autonomous task contract
- Controlled actions and lifecycle statuses
- Human approval requirement
- Explicit prohibition on automated trade execution
- Deterministic cycle contract
- Contract tests

## Safety boundaries

- The module may observe, research, review, alert, or take no action.
- It must not place, modify, or cancel trades.
- Actionable tasks require evidence references.
- Completion requires recorded human approval.
- Deterministic MIS services remain authoritative.

## Next slices

1. Deterministic task planner
2. Approval ledger
3. Idempotent cycle runner
4. Audit trail and recovery
5. Telegram review and approval summaries
6. End-to-end integration tests
