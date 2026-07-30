# Sprint 9 — Company Intelligence

## Objective

Build a deterministic company-intelligence layer that converts verified company evidence into a reusable dossier without changing the production V2 scanner or the Sprint 8 portfolio-review authority model.

## Scope

Sprint 9 will add:

1. Company dossier contracts and versioned storage.
2. Evidence-source registry with provenance and freshness metadata.
3. Deterministic company profile builder.
4. Material-event classification.
5. Evidence completeness and stale-data scoring.
6. Optional LLM interpretation only after evidence validation.
7. Tests, workflow isolation, and operational documentation.

## Non-goals

- No automated trade execution.
- No replacement of scanner entry, stop-loss, or exit logic.
- No invented financial metrics or news.
- No unrestricted web scraping.
- No direct modification of active portfolio positions.

## Proposed flow

```text
Symbol request
    ↓
Evidence registry
    ↓
Verified company evidence
    ↓
Completeness/freshness validation
    ↓
Deterministic dossier
    ↓
Optional evidence-bound LLM interpretation
    ↓
Versioned company report
```

## Initial artifacts

```text
data/company_intelligence_queue.json
reports/company/SYMBOL/YYYY-MM-DD.json
reports/company/SYMBOL/latest.json
```

## Sprint slices

- 9A: Domain contracts and dossier schema
- 9B: Evidence registry and provenance
- 9C: Profile builder
- 9D: Material-event classifier
- 9E: Freshness/completeness scoring
- 9F: Prompt and provider integration
- 9G: Validation and repository
- 9H: Workflow, tests, deployment

## Safety invariant

Every statement about a company must be traceable to supplied evidence. Missing or stale evidence must produce `UNKNOWN`, `NOT_REVIEWED`, or `INSUFFICIENT_DATA` rather than an inferred fact.
