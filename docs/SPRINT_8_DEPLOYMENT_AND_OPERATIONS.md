# Sprint 8 — Portfolio Intelligence Deployment and Operations

## Purpose

Sprint 8 adds a monthly, evidence-bound AI review layer for active portfolio holdings. It does not replace scanner rankings, lifecycle rules, stop-losses, targets, or mechanical exits.

## Deployment sequence

1. Merge PR #8 into `main` only after all tests pass.
2. Add at least one repository secret:
   - `GEMINI_API_KEY`
   - `GROQ_API_KEY`
3. Optionally add repository variables:
   - `LLM_PROVIDER=gemini`
   - `LLM_FALLBACK_PROVIDER=groq`
   - `GEMINI_MODEL=gemini-2.0-flash`
   - `GROQ_MODEL=llama-3.3-70b-versatile`
   - `PORTFOLIO_REVIEW_MAX_AGE_DAYS=45`
   - `PORTFOLIO_REVIEW_MAX_SYMBOLS=30`
   - `PORTFOLIO_REVIEW_MAX_PROVIDER_CALLS=60`
4. Run **Monthly Portfolio Review** manually with `generate_reviews=false`.
5. Confirm queue, health JSON, health message and workflow artifacts are produced.
6. Run again with `generate_reviews=true` for one or two holdings first.
7. Review generated JSON for evidence discipline before enabling normal monthly operation.

## Manual commands

```bash
python -m pytest \
  tests/test_portfolio_reader.py \
  tests/test_review_contracts.py \
  tests/test_review_runner.py \
  tests/test_portfolio_health.py \
  tests/test_review_policy.py \
  tests/test_portfolio_review_integration.py -q

python scripts/run_monthly_portfolio_review.py --period 2026-08
python scripts/build_portfolio_health.py
python scripts/validate_portfolio_intelligence.py
```

After provider secrets are configured:

```bash
python scripts/run_portfolio_reviews.py --max-symbols 2
python scripts/build_portfolio_health.py
python scripts/validate_portfolio_intelligence.py --strict-secrets
```

## Generated outputs

- `data/review_queue.json`
- `data/portfolio_review_run.json`
- `data/portfolio_review_recovery.json`
- `data/portfolio_health.json`
- `data/portfolio_health_message.txt`
- `reports/portfolio/<SYMBOL>/<YYYY-MM>.json`
- `reports/portfolio/<SYMBOL>/latest.json`

## Failure handling

- A provider failure is isolated to the affected symbol.
- Invalid JSON is rejected before persistence.
- Unsupported fundamental or management conclusions are rejected.
- Fresh reviews are reused until the configured age limit.
- A failed review never alters `portfolio.json` or trading rules.
- `portfolio_health.json` remains available with pending or insufficient-data states.

## Rollback

Disable the scheduled workflow or set manual runs to `generate_reviews=false`. The V2 daily scanner and portfolio lifecycle remain operational because Sprint 8 is an independent review layer.

To remove the feature completely, revert the Sprint 8 merge commit. Existing monthly report files may be retained as historical records or removed separately.

## Operational ownership

Monthly checks should confirm:

- workflow completed
- no invalid review JSON
- failed symbols recorded in recovery manifest
- health file active count matches portfolio active count
- Telegram Message 3 contains the stop-loss authority disclaimer
- provider call volume remains within budget

## Acceptance criteria

Sprint 8 is production-ready when:

- all automated tests pass
- readiness validator passes
- one dry run without providers succeeds
- one controlled live-provider run succeeds
- generated report passes strict validation
- portfolio health and Telegram message render correctly
- existing V2 validation remains green
