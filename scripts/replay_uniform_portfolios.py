"""Reconstruct isolated PAPER accounting from archived Git signal reports.

This tests accounting/execution on actual archived signals, not signal quality.
Uses the selected local metadata snapshot and reports that limitation explicitly.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from portfolio_accounting.service import update_portfolio, write_reports
from v2.database import V2Database


def archived(path: str, ref: str, count: int) -> dict:
    commits = subprocess.check_output(['git', 'log', f'-{count}', '--format=%H', ref, '--', path], cwd=ROOT, text=True).split()
    reports = {}
    for commit in commits:
        report = json.loads(subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT, text=True, encoding='utf-8'))
        day = report['as_of_date']
        reports.setdefault(day, (commit, report))
    return reports


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--ref', default='origin/main')
    parser.add_argument('--commits', type=int, default=30)
    args = parser.parse_args()
    out = Path(args.output)
    database = V2Database(args.db)
    evidence = {'kind': 'ACCOUNTING_RECONSTRUCTION_NOT_STRATEGY_BACKTEST',
                'metadata': 'Selected local metadata snapshot; not a fully historical universe reconstruction',
                'scanners': {}}
    for scanner, source in [('Penny', 'output/penny_microcap/daily.json'), ('Momentum Ladder', 'output/old_nse_hull_daily.json')]:
        reports = archived(source, args.ref, args.commits)
        name = scanner.lower().replace(' ', '_')
        history = []
        for day, (sha, report) in sorted(reports.items()):
            snapshot = update_portfolio(scanner, report, database, out / (name + '.sqlite'),
                                        provenance='RECONSTRUCTED_FROM_ARCHIVED_SIGNALS')
            write_reports(snapshot, out / day)
            history.append({'date': day, 'source_commit': sha, 'signal_file': source,
                            **{k: snapshot[k] for k in ('open_positions', 'pending_setups', 'closed_positions',
                                 'equity', 'total_pnl', 'reconciliation_residual', 'events_today')}})
            print(f"{scanner} {day}: open={snapshot['open_positions']} pending={snapshot['pending_setups']}", flush=True)
        if history:
            write_reports(snapshot, out / 'latest')
        evidence['scanners'][scanner] = history
    out.mkdir(parents=True, exist_ok=True)
    (out / 'replay_evidence.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
