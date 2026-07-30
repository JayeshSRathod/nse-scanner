# Sprint 8K–8M: Workflow, Recovery and Cost Controls

## Review freshness

A validated `latest.json` is reused while it is younger than the configured maximum age. The default is 45 days.

- `PORTFOLIO_REVIEW_MAX_AGE_DAYS=45`
- Manual runs may set `force_refresh=true`.
- Missing, malformed or stale reviews are automatically queued.

## Provider-call budget

The monthly process limits both portfolio size and worst-case provider calls.

- `PORTFOLIO_REVIEW_MAX_SYMBOLS=30`
- `PORTFOLIO_REVIEW_MAX_PROVIDER_CALLS=60`

A symbol is skipped before an API call when the run budget is exhausted. Skipping never modifies the mechanical portfolio lifecycle.

## Failure isolation

Each symbol is processed independently. Primary-provider failure falls back to the configured secondary provider. A failed symbol does not prevent health output, artifact upload or persistence of successful reviews.

The workflow records:

- `data/portfolio_review_run.json`
- `data/portfolio_review_recovery.json`

The recovery manifest lists failed and skipped symbols and indicates whether a retry is required.

## GitHub Actions behavior

The AI step uses `continue-on-error`. Consolidated portfolio health and artifacts are generated under `always()`. The final workflow step reports a failure only after all recoverable output has been saved and committed.

## Operational principle

AI reviews are advisory. Existing stop-loss, target and position-lifecycle rules remain authoritative at all times.
