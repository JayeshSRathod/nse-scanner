# Penny EMA14/21 research profile

PR #44 selected a daily Momentum Ladder profile; it did not validate the same
parameters for low-priced stocks. This Penny adaptation is a dry-run PAPER
comparison, separate from the scheduled Penny scanner and its ledger.

Run against the same restored market database as the daily scanner:

```bash
python scripts/run_penny_microcap_daily.py --db nse_scanner.db \
  --ladder-inspired --uniform-portfolio-dir '' \
  --output output/penny_microcap/ladder_inspired_research.json
```

It preserves Penny's ₹1–₹49.99 universe, hard tradeability, market-cap,
delivery, turnover, breakout, extension, circuit and 12% maximum initial stop
gates. READY also requires EMA14 above EMA21 with an upward crossover in the
last five observed sessions. It adds 10 score points for latest volume at least
1.8 times the *prior* 20-session mean, and eight for RSI14 between 50 and 70.
The score remains capped at 100. These are evidence weights, not independent
entry permissions. The existing 75-point READY threshold remains. The existing
Penny T1/T2 and ledger exit logic are unchanged.

The command refuses Telegram sending and uniform portfolio writes. The
scheduled workflow now activates the selected profile and starts a separate
forward PAPER ledger at `paper_portfolios/penny_ema14_21.sqlite`. It writes
the active `penny.json` and `penny.html` reports from that ledger. The former
`penny.sqlite` history is retained without migration. The daily scanner still
sends PAPER messages through the existing Penny bot and topics. The crossover
gate applies to new READY signals; positions entered in the previous ledger
are not silently carried into the new cohort. Review both ledgers when assessing
combined exposure. The workflow runs at 05:15 IST on weekdays; its source data
are the latest restored completed daily snapshots.
