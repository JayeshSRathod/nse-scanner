# Sprint 3 Status — Setup and Fresh Scanner Engine

## Implemented

- breakout detector;
- HMA pullback detector;
- ATR compression detector;
- volume and delivery participation scoring;
- resistance-aware entry, stop, T1 and T2 construction;
- maximum-entry-extension control;
- minimum reward/risk control;
- transparent candidate score;
- reasons for and against every candidate;
- stale-data and bear-regime hard overrides;
- horizon grouping;
- Message 1 text preview;
- isolated unit-test workflow.

## Selection model

Candidate score:

- setup quality: 45%;
- volume/delivery participation: 25%;
- market regime: 20%;
- valid trade plan: 10%.

Hard blocks override the numeric score:

- stale market data;
- BEAR market regime;
- invalid or inadequate trade plan.

## Explicit boundaries

- static sector bias is not used;
- sector-relative score remains disabled until official sector-index history is persisted;
- fundamentals are not yet part of the Sprint 3 score;
- shortlist removal will not become an exit rule; portfolio lifecycle begins in Sprint 4.

## Exit-gate position

The code-level Sprint 3 deliverables are implemented. Final empirical calibration requires running the workflow against the 420-session repository market history and reviewing candidate counts, score distribution and resistance rejections before production use.
