# Sprint 11 — Opportunity Intelligence

## Objective

Build an evidence-bound opportunity layer that converts validated technical, company, market, valuation, catalyst, and risk evidence into ranked investment candidates without changing production scanner or trade-execution logic.

## Initial flow

```text
Scanner candidates
    ↓
Company Intelligence evidence
    ↓
Market Intelligence context
    ↓
Opportunity evidence validation
    ↓
Deterministic scoring and qualification
    ↓
Ranked opportunity candidates
    ↓
Optional evidence-bound explanation
```

## Controlled statuses

- `QUALIFIED`
- `WATCHLIST`
- `REJECTED`
- `INSUFFICIENT_DATA`

## Horizons

- `SHORT`
- `SWING`
- `POSITIONAL`
- `LONG_TERM`

## Sprint slices

- 11A: Domain contracts and safety invariants
- 11B: Evidence assembler
- 11C: Deterministic multi-factor scoring
- 11D: Catalyst and change detection
- 11E: Ranking, diversification, and conflict handling
- 11F: Opportunity repository and versioned output
- 11G: Telegram and dashboard payloads
- 11H: Integration tests, workflow, and deployment

## Safety invariants

1. Every qualified candidate must cite validated evidence.
2. Missing evidence remains explicit and lowers confidence.
3. AI may explain a candidate but cannot create its score or source facts.
4. No order placement or automatic trading is introduced.
5. Opportunity scores must remain deterministic, bounded, and auditable.
