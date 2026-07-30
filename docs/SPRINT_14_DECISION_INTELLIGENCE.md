# Sprint 14 — Decision Intelligence

## Objective

Create the deterministic synthesis layer for the Market Intelligence Suite (MIS). Decision Intelligence combines outputs from Technical, Company, Market, Opportunity, Portfolio, and Research modules without allowing an LLM to create evidence, scores, prices, or portfolio weights.

## Initial flow

```text
Validated MIS module outputs
        ↓
Decision input contract
        ↓
Completeness and conflict checks
        ↓
Deterministic component scoring
        ↓
Policy and portfolio constraints
        ↓
Decision recommendation
        ↓
Evidence-bound explanation
```

## Initial contracts

`DecisionInput` records:

- decision identity and date
- decision scope and subject
- source modules
- unique evidence references

`DecisionRecommendation` records:

- controlled status and action
- bounded deterministic score
- component scores
- confidence
- rationale
- evidence references
- constraints and limitations

## Safety invariants

- `READY` recommendations require evidence, rationale, and a deterministic score.
- Buy, add, reduce, and exit actions require `READY` status.
- Insufficient or conflicting evidence can only produce `WATCH` or `NO_ACTION`.
- Scores must remain between 0 and 100.
- The LLM may explain a validated recommendation but cannot alter the action or score.
- No automated trade execution is introduced.

## Sprint slices

- 14A: Domain contracts and safety rules
- 14B: Decision evidence resolver
- 14C: Completeness and conflict engine
- 14D: Deterministic component scoring
- 14E: Policy and portfolio constraint engine
- 14F: Decision composer
- 14G: Evidence-bound explanation layer
- 14H: Repository, workflow, integration tests, and deployment

## Validation

```bash
python -m pytest tests/test_decision_intelligence_models.py -q
```
