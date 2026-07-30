# Sprint 12 — Portfolio Intelligence 2.0

## Objective

Extend MIS portfolio intelligence from periodic review summaries into deterministic portfolio risk, allocation, diversification, and evidence-bound rebalancing support.

## Initial foundation

- Portfolio risk snapshot contract
- Concentration and diversification bounds
- Controlled risk statuses
- Evidence-bound rebalance proposals
- Directional weight validation
- Explicit insufficient-data behavior

## Planned slices

1. Position and allocation normalizer.
2. Concentration, sector exposure, and diversification engine.
3. Correlation and volatility adapter using verified market data.
4. Risk-budget policy and constraint registry.
5. Deterministic rebalance proposal builder.
6. Scenario and drawdown analysis.
7. Portfolio health integration and Telegram rendering.
8. Repository, workflow, integration tests, and operations guide.

## Safety invariants

- No order placement or automated trading.
- No proposal without evidence and deterministic policy rationale.
- Missing prices, classifications, or risk inputs produce `INSUFFICIENT_DATA`.
- LLMs may explain validated outputs but cannot calculate or override portfolio weights.
