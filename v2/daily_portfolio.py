"""Apply completed daily bars to all persistent V2 positions."""
from __future__ import annotations

from collections.abc import Mapping

from .lifecycle import Position
from .lifecycle_processor import ProcessedEvent, process_daily_bar
from .portfolio_store import PortfolioStore


def process_portfolio_day(
    store: PortfolioStore,
    trade_date: str,
    bars_by_symbol: Mapping[str, Mapping[str, float]],
    *,
    qualification_by_symbol: Mapping[str, bool] | None = None,
    invalidated_symbols: set[str] | None = None,
    partial_fraction: float = 0.5,
    skip_processed_session: bool = False,
) -> dict[str, list[ProcessedEvent]]:
    """Process every non-terminal position and persist each state transition."""
    qualification_by_symbol = qualification_by_symbol or {}
    invalidated_symbols = invalidated_symbols or set()
    output: dict[str, list[ProcessedEvent]] = {}
    processed = set()
    if skip_processed_session:
        with store.connect() as conn:
            processed = {r[0] for r in conn.execute(
                "SELECT DISTINCT trade_id FROM v2_position_events WHERE event_date=? "
                "AND event_type IN ('ENTER','MARK','TRAIL','T1_HIT','STOP_HIT','T2_HIT','CANCEL')",
                (trade_date,),
            )}

    for position in store.open_positions():
        if position.trade_id in processed:
            continue
        bar = bars_by_symbol.get(position.symbol)
        if bar is None:
            continue
        events = process_daily_bar(
            position,
            trade_date,
            bar,
            qualified=qualification_by_symbol.get(position.symbol, True),
            invalidated=position.symbol in invalidated_symbols,
            partial_fraction=partial_fraction,
        )
        for event in events:
            store.save_position(
                event.position,
                event_type=event.event_type,
                previous_state=event.previous_state,
                price=event.price,
            )
        if events:
            output[position.trade_id] = events
            final = events[-1].position
            if final.state.value in {"CLOSED", "CANCELLED"}:
                store.deactivate_watch(final.symbol, final.horizon, final.reason)
    return output
