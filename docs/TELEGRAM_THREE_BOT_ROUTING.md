# Three-Bot Telegram Routing

The repository shares market and corporate data, but every scanner has a fail-closed Telegram route. A missing scanner-specific credential stops that delivery; it never falls back to another bot.

## V3 — NSE Scanner V3

- `V3_TELEGRAM_BOT_TOKEN`
- `V3_TELEGRAM_CHAT_ID`
- `V3_DAILY_TOPIC_ID`
- `V3_PORTFOLIO_TOPIC_ID`
- `V3_WEEKLY_TOPIC_ID`
- `V3_MONTHLY_TOPIC_ID`
- `V3_SYSTEM_TOPIC_ID`

## Momentum Ladder — upgraded Old NSE multi-horizon

- `LADDER_TELEGRAM_BOT_TOKEN`
- `LADDER_TELEGRAM_CHAT_ID`
- `LADDER_DAILY_TOPIC_ID`
- `LADDER_PORTFOLIO_TOPIC_ID`
- `LADDER_VALIDATION_TOPIC_ID`
- `LADDER_REVIEW_TOPIC_ID`
- `LADDER_SYSTEM_TOPIC_ID`

## Hull Pine — existing `@nsescanner_live_bot`

- `HULL_TELEGRAM_BOT_TOKEN`
- `HULL_TELEGRAM_CHAT_ID`
- `HULL_DAILY_TOPIC_ID`
- `HULL_PORTFOLIO_TOPIC_ID`
- `HULL_REVIEW_TOPIC_ID`
- `HULL_SYSTEM_TOPIC_ID`

All values are GitHub Actions secrets. Do not add tokens or IDs to source files. Create and validate the new topics before removing legacy secrets or deleting old topics.
