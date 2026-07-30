# Market Intelligence Suite (MIS) — Sprint 9 Company Intelligence

## Objective

Build a deterministic company-intelligence layer that converts verified company evidence into a reusable dossier without changing the production scanner or Sprint 8 portfolio authority model.

## Scope

Sprint 9 adds:

1. Company dossier contracts and versioned storage.
2. Evidence registry with provenance and freshness controls.
3. Deterministic company profile builder.
4. Material-event classification.
5. Evidence completeness and stale-data scoring.
6. Optional LLM interpretation only after evidence validation.
7. Tests, workflow isolation, and operational documentation.

## Non-goals

- No automated trade execution.
- No replacement of scanner entry, stop-loss, ranking, or exit logic.
- No invented financial metrics or news.
- No unrestricted web scraping.
- No direct modification of active portfolio positions.

## Evidence-first flow

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

## Sprint 9A — Foundation

- Company evidence and dossier contracts
- Controlled evidence and dossier statuses
- Validation against unsupported assumptions

## Sprint 9B — Evidence Platform

Implemented components:

- `EvidenceRegistry` for deterministic validation and registration
- SHA-256 evidence fingerprints for duplicate prevention
- Explicit symbol normalization and category controls
- Provenance requirement for verified evidence
- Future-date rejection
- Latest, category, history, and stale-evidence queries
- `EvidenceRepository` for append-only JSON persistence
- Symbol/year/month/category partitioning
- Atomic filesystem writes
- Repository round-trip and contract tests

Storage layout:

```text
company_data/
  SYMBOL/
    evidence/
      YYYY/
        MM/
          category_<evidence-id>.json
```

## Safety invariant

Every statement about a company must be traceable to supplied evidence. Missing or stale evidence must produce `UNKNOWN`, `NOT_REVIEWED`, or `INSUFFICIENT_DATA` rather than an inferred fact.

Verified evidence requires a source reference, and existing evidence files are never overwritten.

## Validation

```bash
python -m pytest tests/test_company_intelligence_models.py tests/test_evidence_registry.py -q
```

## Remaining slices

- 9C: Deterministic Company Dossier Builder
- 9D: Material-event classifier
- 9E: Freshness/completeness scoring
- 9F: Prompt and provider integration
- 9G: Dossier validation and repository
- 9H: Workflow, integration tests, and deployment
