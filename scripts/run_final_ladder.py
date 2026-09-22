"""Selected daily Momentum Ladder profile; delivery only with explicit flag."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from old_nse_hull.final_ladder.engine import run
from old_nse_hull.final_ladder.render import daily_messages
from portfolio_accounting.service import write_reports
from old_nse_hull.delivery import send_message

def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser();p.add_argument('--db',default='nse_scanner.db');p.add_argument('--ledger',default='paper_portfolios/momentum_ladder_final.sqlite')
    p.add_argument('--output',default='output/old_nse_hull_daily.json');p.add_argument('--portfolio-dir',default='paper_portfolios');p.add_argument('--send-telegram',action='store_true');a=p.parse_args()
    report=run(a.db,a.ledger)
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    tmp=out.with_suffix('.tmp');tmp.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8');tmp.replace(out)
    cards=daily_messages(report);Path('output/old_nse_hull_daily.html').write_text('\n<hr/>\n'.join(cards),encoding='utf-8')
    portfolios=write_reports(report['uniform_portfolio'],a.portfolio_dir)
    # Avoid presenting TP2 as an exit on final-profile portfolio cards.
    portfolios=[m.replace(' | T2:', ' | TP2 reference:') for m in portfolios]
    for m in cards:print(m)
    print(json.dumps({'profile':report['strategy_profile'],'as_of_date':report['as_of_date'],'qualified':report['qualified'],'open_positions':report['uniform_portfolio']['open_positions']}))
    if a.send_telegram:
        for kind,messages in [('radar',cards),('trades',portfolios)]:
            for message in messages:
                result=send_message(message,kind)
                print(f'[TELEGRAM] {kind}: {"SENT" if result.sent else "FAILED"} ({result.reason})')
                if not result.sent:return 2
    return 0

if __name__=='__main__':raise SystemExit(main())
