# NSE Penny & Microcap Shadow Scanner

This is an independent PAPER research system. It does not alter or share
candidate state, paper positions, Telegram credentials, or performance with
V3, Momentum Ladder, Old NSE Hull, or Pine Hull.

## Progressive selection

1. `EARLY_RADAR` detects a developing move with at least 120 sessions, ₹25 lakh
   median 20-day turnover, positive short momentum, and at least two early
   interest conditions. Market cap and delivery can be unverified here.
2. `CONFIRMING` requires at least 180 sessions, ₹50 lakh median turnover,
   price above a rising EMA20, sustained participation, and acceptable distance
   from the trigger.
3. `READY` requires at least 260 sessions, verified market cap of ₹100 crore,
   ₹1 crore median turnover, ₹2 crore recent turnover, delivery confirmation,
   trend and breakout confirmation, controlled distance, a valid stop, and no
   circuit-lock proxy.

`CIRCUIT_LOCKED` and `EXTENDED` remain visible in the Circuit & Risk topic and
can never be treated as READY.

## Dedicated Telegram bot

Create a separate BotFather bot and a forum group named `NSE Penny & Microcap
Shadow`. Create these topics:

- 🪙 Daily Radar
- 🚧 Circuit & Risk
- 📂 Paper Portfolio
- 🔬 Validation
- 📅 Weekly–Monthly Review
- ⚙️ System Health

Add these repository secrets without deleting any existing secrets:

```text
PENNY_TELEGRAM_BOT_TOKEN
PENNY_TELEGRAM_CHAT_ID
PENNY_DAILY_TOPIC_ID
PENNY_RISK_TOPIC_ID
PENNY_PORTFOLIO_TOPIC_ID
PENNY_VALIDATION_TOPIC_ID
PENNY_REVIEW_TOPIC_ID
PENNY_SYSTEM_TOPIC_ID
```

The initial daily workflow sends only Daily Radar and Circuit & Risk. Portfolio,
Validation and Review routes are reserved for their isolated lifecycle sprints.

## Local dry run

```powershell
python .\scripts\run_penny_microcap_daily.py --db nse_scanner.db
```

Inspect `output/penny_microcap/daily.json`. It contains the selected candidates,
all universe rejection reasons, raw metrics, readiness gates, and rendered
delivery status.

## Telegram test

After the dedicated secrets exist, manually dispatch `Penny Microcap Shadow
Daily` with `send_telegram=false`. Inspect the artifact first. Then dispatch
with `send_telegram=true` and verify that Daily Radar and Circuit & Risk reach
only the dedicated penny forum.

## Validation policy

Keep the system in PAPER mode for at least 60 completed NSE sessions. Do not
activate live trading automatically. Circuit proxies are derived from EOD data
and therefore mean “entry unavailable/unverified,” not confirmed order-book
conditions.
