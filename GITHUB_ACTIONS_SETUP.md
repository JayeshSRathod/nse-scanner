# GitHub Actions setup for NSE Scanner

## Required repository secrets

Create these in **Settings → Secrets and variables → Actions**:

- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`
- `ADMIN_CHAT_ID`
- `NSE_REPO_TOKEN`  (PAT with `repo` scope; used by pipeline to push JSON outputs)
- `GITHUB_REPO`     (example: `JayeshSRathod/nse-scanner`)
- `GITHUB_BRANCH`   (example: `main`)

## Workflows

All workflows use:
- `actions/checkout@v6`
- `actions/setup-python@v6`
These versions are aligned with Node.js 24 runtime migration on GitHub-hosted runners.

1. `nse-pipeline.yml`
   - Runs `python main_pipeline.py`
   - Schedule default: weekdays 01:00 UTC (edit if needed)
   - Manual run supports selecting a git ref/branch input

2. `nse-admin-reports.yml`
   - Runs health and users reports at:
     - `0 18 * * 1-5` (11:30 PM IST)
     - `5 18 * * 1-5` (11:35 PM IST)
   - Can also run manually and choose `health`, `users`, or `both`

3. `nse-bot-smoke.yml`
   - Manual startup check for `main.py` (90-second smoke run)
   - Marked pass only if bot stays alive for 90 seconds
   - Use this only for validation. Long-running polling bot should run on a persistent host.

## Important

GitHub Actions is ideal for cron/batch jobs (pipeline + reports).
For the Telegram polling bot (`main.py`), keep using a persistent host (Railway/Render/VPS), because Actions jobs stop after timeout.

## Troubleshooting

- If a workflow fails quickly with `Missing required secrets`, set the secret in
  repository settings and re-run.
- `NSE_REPO_TOKEN` should be a PAT with `repo` scope so pipeline API commits can succeed.
