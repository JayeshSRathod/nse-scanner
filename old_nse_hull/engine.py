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
from .multi_horizon.config import shadow_enabled
from .multi_horizon.engine import run_shadow
from v2.database import V2Database
from v2.tradeability import evaluate_tradeability, summarize as summarize_tradeability


def _wma(series: pd.Series, length: int) -> pd.Series:
    weights = list(range(1, length + 1))
    return series.rolling(length).apply(lambda values: float((values * weights).sum() / sum(weights)), raw=True)


def _hma(series: pd.Series, length: int) -> pd.Series:
    return _wma(2 * _wma(series, length // 2) - _wma(series, length), int(length ** 0.5))


def _tradeable_prices(prices: pd.DataFrame, db_path: str | Path) -> tuple[pd.DataFrame, dict]:
    """Apply the common current-security gate before either Old+Hull path.

    The Old+Hull system retains independent PAPER scoring and state; it only
    shares the read-only universe safety gate used by the other scanners.
    """
    if prices.empty:
        return prices, {"evaluated": 0, "eligible": 0, "rejected": 0}
    trade_date = pd.Timestamp(prices["trade_date"].max()).date().isoformat()
    database = V2Database(db_path)
    master = database.load_symbol_master(trade_date)
    metadata = {str(row["symbol"]): row.to_dict() for _, row in master.iterrows()} if not master.empty else {}
    restricted = database.load_restricted_symbols(trade_date)
    lifecycle_registry = database.load_lifecycle_registry()
    session_calendar = tuple(sorted(pd.to_datetime(prices["trade_date"]).dt.date.astype(str).unique()))
    gateway = {
        str(symbol): evaluate_tradeability(
            str(symbol), frame, market_date=trade_date, master_row=metadata.get(str(symbol)),
            restricted_reason=restricted.get(str(symbol)), lifecycle_event=lifecycle_registry.get(str(symbol)),
            session_calendar=session_calendar, require_metadata=bool(metadata),
        )
        for symbol, frame in prices.groupby("symbol", sort=True)
    }
    allowed = {symbol for symbol, result in gateway.items() if result.eligible and not result.entry_blocked}
    return prices[prices["symbol"].astype(str).isin(allowed)].copy(), summarize_tradeability(gateway)


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
    aligned_count = sum(states.values())
    confirmed = bool(states["daily"] and aligned_count >= 3)
    return {"timeframes": states, "aligned_count": aligned_count,
            "aligned": confirmed, "state": "CONFIRMING" if confirmed else "WATCH"}


def run_local(db_path: str = "nse_scanner.db", as_of: str | None = None, top_n: int = 25,
              comparison_state_path: str | Path | None = None, paper_state_path: str | Path | None = None) -> dict:
    """Run the frozen baseline; optionally attach a non-delivered shadow comparison."""
    prices = load_market_data(db_path, as_of)
    prices, tradeability = _tradeable_prices(prices, db_path)
    result = discover(prices, top_n=top_n)
    rows = result.shortlist.to_dict(orient="records")
    frames = {symbol: frame for symbol, frame in prices.groupby("symbol")}
    for row in rows:
        confirmation = alignment(frames[row["symbol"]])
        ready = bool(row["discovery_score"] >= 75 and confirmation["aligned"])
        row.update({"hull_state": "READY" if ready else confirmation["state"],
                    "timeframes": confirmation["timeframes"],
                    "paper_entry_enabled": ready,
                    "reason": "python_hull_rules_active"})
    report = {"system": "OLD_NSE_HULL_PAPER", "generated_at": datetime.now().astimezone().isoformat(),
            "as_of_date": result.as_of_date, "parity": "PYTHON_RULES_ACTIVE", "paper_entries_enabled": True,
            "eligible": result.eligible, "discovery_qualified": len(rows), "ready": sum(r["hull_state"] == "READY" for r in rows),
            "watch": sum(r["hull_state"] == "WATCH" for r in rows), "rejected": result.rejected, "shortlist": rows,
            "state": "PAPER_EOD_ACTIVE", "tradeability": tradeability}
    if shadow_enabled():
        # The report artifact is the comparison surface during the 20-session
        # evaluation. It never changes the baseline shortlist or Telegram UX.
        report["multi_horizon_shadow"] = run_shadow(prices, db_path, [row["symbol"] for row in rows], comparison_state_path, paper_state_path)
    return report


def render_radar(report: dict) -> str:
    lines = ["🧪 <b>OLD NSE + HULL — DAILY RADAR</b>", "<b>PAPER SYSTEM</b>",
             f"<b>Data:</b> {report.get('as_of_date') or 'N/A'} EOD",
             f"<b>Generated:</b> {report['generated_at']}", "",
             f"Eligible EQ stocks: {report['eligible']}", f"Discovery qualified: {report['discovery_qualified']}",
             f"Watch for entry: {report['ready']}", f"Wait for confirmation: {report['watch']}", "",
             "Hull rules: <b>PYTHON EOD ACTIVE</b>",
             "Watch for entry means the trend is aligned; wait for the stated trigger.",
             "", "⚠️ <b>Paper-only output</b>",
             "• This is a research shortlist, not a live-trading instruction.",
             "• Watch-for-entry candidates are eligible for the separate paper lifecycle."]
    if report["shortlist"]:
        lines.extend(["", "<b>Discovery shortlist</b>"])
        for row in report["shortlist"][:10]:
            aligned = ", ".join(name.upper() for name, ok in row.get("timeframes", {}).items() if ok) or "none"
            label = "Watch for entry" if row.get("hull_state") == "READY" else "Watchlist—wait for confirmation"
            signals = ", ".join(str(item).replace("_", " ") for item in row.get("early_signals", ())[:2])
            reason = signals or "movement structure improving"
            lines.append(f"• <b>{row['symbol']}</b> — opportunity {row['discovery_score']:.1f}/100 | {label} | {reason}")
    return "\n".join(lines)


def render_paper_trades(report: dict) -> str:
    """Separate Paper Trades topic; READY is explicitly not an entry."""
    ready = [row for row in report["shortlist"] if row.get("hull_state") == "READY"]
    lines = ["🧭 <b>OLD+HULL — PAPER TRADE LIFECYCLE</b>",
             f"<b>Data:</b> {report.get('as_of_date') or 'N/A'} EOD", "",
             f"Ready setups: {len(ready)}", "Triggered today: 0", "Active paper trades: 0", "Exited today: 0", ""]
    if not ready:
        lines.append("No watch-for-entry setups today. No paper entry was created.")
    for row in ready[:5]:
        symbol = row["symbol"]
        url = f"https://www.tradingview.com/chart/?symbol=NSE%3A{symbol}"
        lines.extend(["━━━━━━━━━━━━━━━━━━", f"🟢 <a href=\"{url}\">{symbol}</a> — WATCH FOR ENTRY — NOT ENTERED",
                      f"Opportunity score: {row['discovery_score']:.1f}/100 | Rank: {row['discovery_rank']}",
                      "Price structure is holding across at least three checked periods", "",
                      "Next step: Wait for the next-session mechanical trigger.",
                      "⚠️ Watch for entry is not a paper entry. It never uses the same closing price; wait for the next-session trigger."])
    lines.extend(["", "💼 <b>OLD+HULL — PAPER PORTFOLIO</b>",
                  "⚠️ SIMULATED RESULTS — NO LIVE ORDERS", "Open paper trades: 0 | Deployed: ₹0.00 | Total P&L: ₹0.00",
                  "Health: ✅ Radar data current · No lifecycle state created yet"])
    return "\n".join(lines)


def render_period_report(report: dict, period: str, shadow_summary: dict | None = None) -> str:
    title = "WEEKLY REVIEW" if period == "weekly" else "MONTHLY VALIDATION"
    lines = [f"📅 <b>OLD NSE + HULL — {title}</b>", "🧪 <b>PAPER SYSTEM</b>",
             f"Latest data: {report.get('as_of_date') or 'N/A'} EOD", "",
             f"Old NSE discovery qualified: {report['discovery_qualified']}",
             f"Watch for entry: {report['ready']} | Wait for confirmation: {report['watch']}",
             "Triggered entries: 0 | Closed paper trades: 0", "",
             "System comparison: N/A — equivalent closed-lifecycle baseline unavailable.",
             "Status: Continue PAPER observation; no live orders."]
    if shadow_summary is not None:
        status = "REVIEW REQUIRED - no automatic promotion" if shadow_summary.get("validation_ready") else "BLOCKED - observation window incomplete"
        lines.extend(["", "<b>Multi-horizon shadow validation</b>",
                      f"Sessions: {shadow_summary.get('sessions_observed', 0)}/{shadow_summary.get('target_sessions', 20)} | Remaining: {shadow_summary.get('sessions_remaining', 20)}",
                      f"Average candidates: baseline {shadow_summary.get('average_baseline_candidates', 0)} | shadow {shadow_summary.get('average_shadow_candidates', 0)} | overlap {shadow_summary.get('average_overlap', 0)}",
                      f"Promotion gate: <b>{status}</b>"])
        for item in shadow_summary.get("recent_sessions", [])[-3:]:
            lines.append(f"- {item['as_of_date']}: baseline {len(item['baseline_symbols'])} | shadow {len(item['shadow_symbols'])} | overlap {len(item['overlap_symbols'])} | new {item.get('newly_qualified', 0)} | upgraded {item.get('upgraded', 0)}")
    return "\n".join(lines)


def save_report(report: dict, output: str | Path) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, indent=2), encoding="utf-8")
