# Sprint 13 — AI Research Assistant

## Objective

Create an evidence-bound conversational research layer for the Market Intelligence Suite (MIS).

## Initial capabilities

- Company research questions
- Company comparisons
- Sector research
- Portfolio questions
- Market-state questions
- Explicit evidence references, confidence, and limitations

## Safety invariants

1. The assistant may summarize and explain validated evidence.
2. It must not create financial facts, prices, scores, portfolio weights, or source records.
3. `READY` answers require evidence references.
4. Missing or stale inputs produce `PARTIAL` or `INSUFFICIENT_DATA`.
5. Deterministic MIS engines remain authoritative for scoring, risk, and ranking.

## Planned flow

```text
Research query
    ↓
Intent and entity resolution
    ↓
Evidence retrieval from MIS modules
    ↓
Freshness and completeness validation
    ↓
Prompt construction
    ↓
Provider abstraction
    ↓
Strict response validation
    ↓
Evidence-linked research answer
```

## Sprint slices

- 13A: Domain contracts and tests
- 13B: Intent and entity resolver
- 13C: Cross-module evidence retriever
- 13D: Research context builder
- 13E: Prompt and provider integration
- 13F: Citation and claim validator
- 13G: Comparison and portfolio research modes
- 13H: CLI, Telegram integration, workflow, and operations
