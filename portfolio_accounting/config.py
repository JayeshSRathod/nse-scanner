"""Single opt-in switch for scheduled portfolio reporting."""
import os


def rollout_directory() -> str | None:
    return 'paper_portfolios' if os.getenv('UNIFORM_PAPER_PORTFOLIOS', '').lower() == 'true' else None
