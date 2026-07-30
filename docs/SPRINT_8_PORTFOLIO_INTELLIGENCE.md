# Sprint 8 — Portfolio Intelligence

## Purpose

Add a monthly intelligence layer for active portfolio holdings while preserving
the existing daily NSE scanner and portfolio lifecycle.

## Delivery sequence

- **8A:** Review data model and persistence
- **8B:** Active portfolio reader and review queue
- **8C:** Verified evidence collector
- **8D:** Prompt builder
- **8E:** Provider-neutral LLM adapter
- **8F:** Strict response validation
- **8G:** Review orchestration
- **8H:** Versioned report repository
- **8I:** Consolidated portfolio health output
- **8J:** Telegram Message 3 integration
- **8K:** Monthly GitHub Actions automation
- **8L:** Retry and provider fallback
- **8M:** Quota and cost controls
- **8N:** Unit and integration tests
- **8O:** Operations documentation

## Current implementation slice

The foundation currently provides:

1. A controlled portfolio-review domain model.
2. A defensive reader for the existing root-level `portfolio.json` file.
3. Symbol-level filtering of active/open positions only.
4. A deterministic monthly `data/review_queue.json` output.
5. Unit tests for filtering, symbol normalization and queue ordering.
6. A manually runnable and monthly scheduled GitHub Actions workflow.

## Command

```bash
python scripts/run_monthly_portfolio_review.py
```

Optional arguments:

```bash
python scripts/run_monthly_portfolio_review.py \
  --portfolio portfolio.json \
  --period 2026-08 \
  --output data/review_queue.json
```

## Safety boundary

This stage does not call an LLM, scrape financial websites, alter positions,
or change Telegram output. Those capabilities will be introduced through the
remaining Sprint 8 sub-sprints after each input/output contract is tested.
