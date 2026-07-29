# Sprint 2 — Regime, Indicators and Relative Strength

## Implementation rule

V2 trading intelligence is implemented from the approved design. Legacy code is consulted only for reusable infrastructure and compatibility risks.

## Implemented foundation

- pure WMA and HMA calculations;
- Hybrid Hull trend-permission state;
- Wilder ATR and ATR percentage;
- HMA extension measured in ATR units;
- benchmark-relative strength ratio and excess return;
- date-explicit BULL, NEUTRAL and BEAR regime classification;
- breadth inputs using percentages above 50-day and 200-day averages;
- unbiased relative-strength ranking with no static sector preference;
- unit-test and isolated GitHub Actions workflow.

## Separation from V1

The V1 loader and production scanner remain compatibility infrastructure. V2 retention settings live in `v2/data_policy.py`; new market intelligence lives under `v2/` and does not call legacy ranking or entry logic.

## Remaining Sprint 2 work

- production index and sector-history adapter;
- breadth builder from the migrated price table;
- stock and sector RS snapshot persistence;
- independent sample reconciliation using actual database symbols;
- final parameter version record.
