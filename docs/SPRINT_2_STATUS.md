# Sprint 2 Status

Implemented:
- pure V2 indicator calculations;
- market regime classifier;
- read-only V1/V2 database adapter;
- market breadth calculation;
- reproducible regime snapshot persistence;
- isolated tests and workflows.

Safety controls:
- V1 trading logic remains frozen;
- V2 modules live under `v2/`;
- production Telegram is not used;
- regime output is date-explicit and idempotent.

Open validation gate:
- run against the real NSE database;
- identify the canonical NIFTY benchmark name in `index_perf`;
- reconcile sample HMA, ATR, breadth and RS values;
- confirm sector-index coverage.
