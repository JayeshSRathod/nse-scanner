"""Generate local-only Old NSE + Hull paper-validation artifacts; never sends Telegram."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Direct script invocation is used by GitHub Actions; make the repository
# package importable without relying on ``python -m`` package semantics.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from old_nse_hull.delivery import send_message, send_radar, send_trades
from old_nse_hull.engine import render_paper_trades, render_radar, run_local, save_report
from old_nse_hull.multi_horizon.telegram import render_messages as render_shadow_messages


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="nse_scanner.db")
    parser.add_argument("--date")
    parser.add_argument("--output", default="output/old_nse_hull_daily.json")
    parser.add_argument("--html", default="output/old_nse_hull_daily.html")
    parser.add_argument("--send-telegram", action="store_true")
    parser.add_argument("--multi-horizon-shadow", action="store_true",
                        help="Enable comparison-only multi-horizon output; Telegram remains baseline-only.")
    parser.add_argument("--shadow-state", default="old_nse_hull_shadow_state.json",
                        help="Git-backed 20-session comparison ledger used only in shadow mode.")
    parser.add_argument("--paper-state", default="old_nse_hull_paper_state.json",
                        help="Git-backed simulated watchlist and paper-position state used only in shadow mode.")
    parser.add_argument("--shadow-preview-html", default="output/old_nse_hull_shadow_preview.html")
    parser.add_argument("--send-shadow-preview", action="store_true",
                        help="Send clearly labelled PAPER shadow cards to the Ladder validation topic.")
    args = parser.parse_args()
    if args.multi_horizon_shadow:
        import os
        os.environ["OLD_NSE_HULL_MULTI_HORIZON_MODE"] = "shadow"
    report = run_local(args.db, args.date, comparison_state_path=args.shadow_state if args.multi_horizon_shadow else None,
                       paper_state_path=args.paper_state if args.multi_horizon_shadow else None)
    save_report(report, args.output)
    message = render_radar(report)
    Path(args.html).write_text(message, encoding="utf-8")
    shadow_messages: list[str] = []
    if args.multi_horizon_shadow:
        shadow_messages = render_shadow_messages(report)
        Path(args.shadow_preview_html).write_text("\n\n<hr/>\n\n".join(shadow_messages), encoding="utf-8")
    print(message)
    if args.send_telegram:
        delivery = send_radar(message)
        trades_delivery = send_trades(render_paper_trades(report))
        print(f"[OLD_NSE_HULL] Radar Telegram: {delivery.reason}; Trades Telegram: {trades_delivery.reason}")
        if not delivery.sent or not trades_delivery.sent:
            return 2
    if args.send_shadow_preview:
        for preview in shadow_messages:
            delivery = send_message(preview, "validation")
            if not delivery.sent:
                print(f"[OLD_NSE_HULL] Shadow preview Telegram: {delivery.reason}")
                return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
