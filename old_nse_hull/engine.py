"""Independent Old NSE discovery and EOD Hull PAPER scanner.

The Python Hull rules are the operating rules for this system. They are not
presented as a TradingView/Pine export or a live-trading instruction.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from .discovery import discover, load_market_data


def _wma(series: pd.Series, length: int) -> pd.Series:
    weights = list(range(1, length + 1))
    return series.rolling(length).apply(lambda values: float((values * weights).sum() / sum(weights)), raw=True)


def _hma(series: pd.Series, length: int) -> pd.Series:
    return _wma(2 * _wma(series, length // 2) - _wma(series, length), int(length ** 0.5))


def alignment(frame: pd.DataFrame) -> dict:
    """Reduced EOD Hull confirmation: visual alignment, not Pine parity."""
    data = frame.sort_values("trade_date").copy()
    close = pd.to_numeric(data["close"], errors="coerce")
    daily_fast, daily_slow = _hma(close, 21), _hma(close, 51)
    states = {"daily": bool(close.iloc[-1] > daily_slow.iloc[-1] and daily_fast.iloc[-1] > daily_slow.iloc[-1] and daily_fast.iloc[-1] > daily_fast.iloc[-2])}
    indexed = data.set_index("trade_date")["close"]
    for label, rule in {"weekly": "W-FRI", "monthly": "ME", "3m": "QE", "6m": "2QE"}.items():
        series = indexed.resample(rule).last().dropna()
        if len(series) < 3:
            states[label] = False
            continue
        fast = _hma(series, min(3, max(2, len(series) // 2)))
        slow = _hma(series, min(5, max(3, len(series) - 1)))
        states[label] = bool(pd.notna(fast.iloc[-1]) and pd.notna(slow.iloc[-1]) and fast.iloc[-1] > slow.iloc[-1] and fast.iloc[-1] >= fast.iloc[-2])
    return {"timeframes": states, "aligned": all(states.values()), "state": "READY" if all(states.values()) else "WATCH"}


def run_local(db_path: str = "nse_scanner.db", as_of: str | None = None, top_n: int = 25) -> dict:
    prices = load_market_data(db_path, as_of)
    result = discover(prices, top_n=top_n)
    rows = result.shortlist.to_dict(orient="records")
    frames = {symbol: frame for symbol, frame in prices.groupby("symbol")}
    for row in rows:
        confirmation = alignment(frames[row["symbol"]])
        row.update({"hull_state": confirmation["state"], "timeframes": confirmation["timeframes"],
                    "paper_entry_enabled": confirmation["state"] == "READY",
                    "reason": "python_hull_rules_active"})
    return {"system": "OLD_NSE_HULL_PAPER", "generated_at": datetime.now().astimezone().isoformat(),
            "as_of_date": result.as_of_date, "parity": "PYTHON_RULES_ACTIVE", "paper_entries_enabled": True,
            "eligible": result.eligible, "discovery_qualified": len(rows), "ready": sum(r["hull_state"] == "READY" for r in rows),
            "watch": sum(r["hull_state"] == "WATCH" for r in rows), "rejected": result.rejected, "shortlist": rows,
            "state": "PAPER_EOD_ACTIVE"}


def render_radar(report: dict) -> str:
    lines = ["🧪 <b>OLD NSE + HULL — DAILY RADAR</b>", "<b>PAPER SYSTEM</b>",
             f"<b>Data:</b> {report.get('as_of_date') or 'N/A'} EOD",
             f"<b>Generated:</b> {report['generated_at']}", "",
             f"Eligible EQ stocks: {report['eligible']}", f"Discovery qualified: {report['discovery_qualified']}",
             f"Hull READY: {report['ready']}", f"Hull WATCH: {report['watch']}", "",
             "Hull rules: <b>PYTHON EOD ACTIVE</b>",
             "READY means daily, weekly, monthly, 3M and 6M Hull alignment.",
             "", "⚠️ <b>Paper-only output</b>",
             "• This is a research shortlist, not a live-trading instruction.",
             "• READY candidates are eligible for the separate paper lifecycle."]
    if report["shortlist"]:
        lines.extend(["", "<b>Discovery shortlist</b>"])
        for row in report["shortlist"][:10]:
            aligned = ", ".join(name.upper() for name, ok in row.get("timeframes", {}).items() if ok) or "none"
            lines.append(f"• <b>{row['symbol']}</b> — discovery {row['discovery_score']:.1f}/100 | {row.get('hull_state', 'WATCH')} | aligned: {aligned}")
    return "\n".join(lines)


def render_paper_trades(report: dict) -> str:
    """Separate Paper Trades topic; READY is explicitly not an entry."""
    ready = [row for row in report["shortlist"] if row.get("hull_state") == "READY"]
    lines = ["🧭 <b>OLD+HULL — PAPER TRADE LIFECYCLE</b>",
             f"<b>Data:</b> {report.get('as_of_date') or 'N/A'} EOD", "",
             f"Ready setups: {len(ready)}", "Triggered today: 0", "Active paper trades: 0", "Exited today: 0", ""]
    if not ready:
        lines.append("No READY setups today. No paper entry was created.")
    for row in ready[:5]:
        symbol = row["symbol"]
        url = f"https://www.tradingview.com/chart/?symbol=NSE%3A{symbol}"
        lines.extend(["━━━━━━━━━━━━━━━━━━", f"🟢 <a href=\"{url}\">{symbol}</a> — READY — NOT ENTERED",
                      f"Discovery: {row['discovery_score']:.1f}/100 | Rank: {row['discovery_rank']}",
                      "Hull: Daily, Weekly, Monthly, 3M and 6M aligned", "",
                      "Next step: Wait for the next-session mechanical trigger.",
                      "⚠️ READY is not a paper entry and never uses the same closing price."])
    lines.extend(["", "💼 <b>OLD+HULL — PAPER PORTFOLIO</b>",
                  "⚠️ SIMULATED RESULTS — NO LIVE ORDERS", "Open paper trades: 0 | Deployed: ₹0.00 | Total P&L: ₹0.00",
                  "Health: ✅ Radar data current · No lifecycle state created yet"])
    return "\n".join(lines)


def render_period_report(report: dict, period: str) -> str:
    title = "WEEKLY REVIEW" if period == "weekly" else "MONTHLY VALIDATION"
    lines = [f"📅 <b>OLD NSE + HULL — {title}</b>", "🧪 <b>PAPER SYSTEM</b>",
             f"Latest data: {report.get('as_of_date') or 'N/A'} EOD", "",
             f"Old NSE discovery qualified: {report['discovery_qualified']}",
             f"Hull READY: {report['ready']} | Hull WATCH: {report['watch']}",
             "Triggered entries: 0 | Closed paper trades: 0", "",
             "System comparison: N/A — equivalent closed-lifecycle baseline unavailable.",
             "Status: Continue PAPER observation; no live orders."]
    return "\n".join(lines)


def save_report(report: dict, output: str | Path) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, indent=2), encoding="utf-8")
