"""Isolated immutable ledger for the selected Ladder profile."""
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from portfolio_accounting.ledger import LedgerConfig
from .execution import apply_exit

def advance(path: str | Path, scanner: str, day: str, bars: dict, candidates: list[dict], *,
            config: LedgerConfig = LedgerConfig(), legacy: list[dict] | None = None,
            provenance: str = 'FORWARD_PAPER_COHORT', previous_session: str | None = None) -> dict:
    """A date is immutable: identical retries return its stored report.

    Different inputs for an already completed date fail rather than replaying
    fills or silently repricing history. One database contains one scanner only.
    """
    if scanner not in {'Penny', 'Momentum Ladder'}:
        raise ValueError("Only Penny and Ladder use this new lifecycle")
    from datetime import date
    date.fromisoformat(day)
    config.validate()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({'bars': bars, 'candidates': candidates, 'config': asdict(config),
                          'scanner': scanner, 'provenance': provenance}, sort_keys=True, allow_nan=False)
    digest = sha256(payload.encode()).hexdigest()
    with sqlite3.connect(target, timeout=30) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS ledger (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)')
        conn.execute('CREATE TABLE IF NOT EXISTS sessions (day TEXT PRIMARY KEY, digest TEXT NOT NULL, report TEXT NOT NULL)')
        conn.commit()
        conn.execute('BEGIN IMMEDIATE')
        existing = conn.execute('SELECT digest, report FROM sessions WHERE day=?', (day,)).fetchone()
        if existing:
            if existing[0] != digest:
                raise ValueError("Completed session inputs changed; use a separate reconstruction ledger")
            return json.loads(existing[1])
        stored = conn.execute('SELECT payload FROM ledger WHERE id=1').fetchone()
        state = json.loads(stored[0]) if stored else {
            'scanner': scanner, 'config': asdict(config), 'positions': [], 'pending': [],
            'events': [], 'last_date': None, 'legacy': legacy or [], 'provenance': provenance,
        }
        if state['scanner'] != scanner or state['config'] != asdict(config) or state['provenance'] != provenance:
            raise ValueError("Ledger identity/configuration cannot change")
        if state['last_date'] and day <= state['last_date']:
            raise ValueError("Cannot append an older session")
        if state['last_date'] and previous_session and state['last_date'] != previous_session:
            raise ValueError("Missing market session; replay the missing dates before advancing")
        state['pending']=[p for p in state['pending'] if p['sessions_waited']<5]
        active={symbol:dict(bar) for symbol,bar in bars.items()}
        for p in state['positions']:
            if p['remaining_quantity'] and p['symbol'] not in active:
                price=p['last_price']
                active[p['symbol']]=dict(date=day,open=price,high=price,low=price,close=price,review_required=True,entry_allowed=False,entry_blocked=True,exit_blocked=True)
        for p in state['pending']:
            if p['symbol'] in active and not active[p['symbol']].get('prior_trend',False):
                active[p['symbol']]['entry_allowed']=False
        result = apply_exit(state, day, active, candidates, config, 'TRAIL_STRUCT')
        conn.execute('INSERT OR REPLACE INTO ledger VALUES (1,?)', (json.dumps(state, allow_nan=False),))
        conn.execute('INSERT INTO sessions VALUES (?,?,?)', (day, digest, json.dumps(result, allow_nan=False)))
        return result
