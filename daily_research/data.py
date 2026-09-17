"""Read-only source loading. Versioned snapshots fill newer database sessions."""
from __future__ import annotations

from pathlib import Path
from hashlib import sha256
import sqlite3
import pandas as pd


def load_sources(db: Path, snapshots: Path, symbols: list[str] | None = None):
    with sqlite3.connect(db.resolve().as_uri()+'?mode=ro', uri=True) as conn:
        sql = 'SELECT symbol,date,open,high,low,close,volume,turnover_lacs,delivery_pct FROM daily_prices'
        params = []
        if symbols:
            sql += ' WHERE symbol IN ('+','.join('?' for _ in symbols)+')'
            params = symbols
        daily = pd.read_sql_query(sql, conn, params=params)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        counts = {t: conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in (
            'fundamental_snapshots_v3', 'corporate_actions_v3', 'governance_events_v3',
            'market_cap_snapshots_v3', 'shareholding_patterns_v3', 'promoter_pledge_v3', 'pe_ratios') if t in tables}
        benchmark = pd.read_sql_query("SELECT date,close FROM index_perf WHERE UPPER(index_name)='NIFTY 500' ORDER BY date", conn) if 'index_perf' in tables else pd.DataFrame()
    original_end = daily.date.max() if len(daily) else None
    chunks = [daily]
    database_dates = set(daily.date)
    for path in sorted(snapshots.glob('*.csv')):
        # Use snapshot dates missing in SQLite, including internal gaps.
        if path.stem in database_dates:
            continue
        part = pd.read_csv(path, usecols=list(daily.columns))
        if not part.date.astype(str).eq(path.stem).all():
            raise ValueError(f'Snapshot filename/date mismatch: {path.name}')
        if symbols:
            part = part.loc[part.symbol.isin(symbols)]
        chunks.append(part)
    combined = pd.concat(chunks, ignore_index=True).rename(columns={'date':'trade_date'})
    if combined.duplicated(['symbol', 'trade_date']).any():
        raise ValueError('Conflicting/duplicate source rows')
    combined = combined.sort_values(['symbol','trade_date'])
    frames = {s: d.reset_index(drop=True) for s, d in combined.groupby('symbol', sort=True)}
    b = benchmark.set_index('date').close if not benchmark.empty else None
    return frames, b, {'sqlite_price_end': original_end, 'combined_price_start': combined.trade_date.min(),
                       'combined_price_end': combined.trade_date.max(), 'symbols': len(frames),
                       'price_rows': len(combined), 'corporate_table_rows': counts,
                       'price_fingerprint': sha256(pd.util.hash_pandas_object(combined, index=False).values.tobytes()).hexdigest(),
                       'benchmark_end': None if benchmark.empty else benchmark.date.max(),
                       'eligibility_status': 'TECHNICAL RESEARCH ONLY; HISTORICAL SECURITY/FUNDAMENTAL ELIGIBILITY NOT CERTIFIED',
                       'unavailable': ['intraday OHLCV', 'volume profile/POC', 'certified historical sector valuation',
                                       'complete monthly/weekly Hybrid Hull warm-up', 'historical circuit executability']}
