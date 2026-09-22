"""Frozen selected settings. Scope is forward PAPER only."""
from portfolio_accounting.ledger import LedgerConfig
PROFILE_ID='LADDER_DAILY_20260922'
VOLUME_MULTIPLE=1.8
RSI_LOWER=50
RSI_UPPER=70
SCORE_MIN=65
EXPIRY_SESSIONS=5
EXCLUDED_SYMBOLS={'UNITDSPR'}
CONFIG=LedgerConfig(fee_bps=10,slippage_bps=5)
