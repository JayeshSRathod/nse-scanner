# Sprint 10 — Market Intelligence

## Objective

Build a deterministic Market Intelligence Suite layer that summarizes market breadth, sector strength, liquidity and volatility from verified evidence without changing production scanner authority.

## Initial slices

- 10A: Market evidence and snapshot contracts
- 10B: Breadth engine
- 10C: Sector-relative-strength engine
- 10D: Liquidity and volatility state
- 10E: Deterministic market-regime classifier
- 10F: Versioned market snapshots
- 10G: Telegram and dashboard outputs
- 10H: Workflow, tests and deployment

## Safety invariant

The market regime must be derived only from validated inputs. Missing, stale or conflicting evidence must produce `INSUFFICIENT_DATA` or explicit limitations instead of an inferred conclusion.
