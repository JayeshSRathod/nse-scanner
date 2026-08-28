# Scanner Selection V2

This release separates discovery, confirmation, timing and execution risk.
It remains an EOD, paper-only research system.

## Shared lifecycle

- Early watchlist: movement is beginning; observe only.
- Watchlist—wait for confirmation: evidence is improving but incomplete.
- Watch for entry: score and setup are valid; wait for the stated trigger.
- New paper entry: the later-session fill rule actually fired.
- Wait for pullback: the setup is valid but price is extended.
- No entry—circuit risk: normal execution is not dependable.

## V3

V3 uses multi-session Hull persistence instead of requiring a perfect latest
daily candle. Price must hold above Hull in at least three of five sessions,
with an improving Hull slope and HMA structure. KAMA remains diagnostic only.
Existing horizon, trigger, stop-distance and reward/risk gates remain active.

## Momentum Ladder

Ladder discovery is based on momentum acceleration, base quality,
participation, trend transition and breakout proximity. Positive 1M or 3M
returns are not hard requirements. At least four independent early-movement
signals are required. A score of 75 plus multi-period structure confirmation
is required for Watch for entry.

## Hull timing

Hull readiness uses three-of-five price persistence, HMA alignment, improving
Hull slope, ADX confirmation, weekly context and a maximum 1.25 ATR extension.
KAMA is not a readiness or lifecycle gate.

## Penny liquidity

- Early watchlist: 20-day median turnover of at least ₹20 lakh.
- Confirmation: median ₹40 lakh and recent five-day average ₹60 lakh.
- Watch for entry: median ₹60 lakh and recent five-day average ₹100 lakh.
- High Liquidity badge: median ₹100 lakh and recent five-day average ₹200 lakh.

Penny READY requires a score of at least 75 and retains the market-cap,
delivery, breakout, stop-risk, circuit and tradeability gates.
