"""Persistent, auditable trade lifecycle state machine for NSE Scanner V2."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from uuid import uuid4


class TradeState(str, Enum):
    WATCH = "WATCH"
    READY = "READY"
    OPEN = "OPEN"
    PARTIAL = "PARTIAL"
    TRAILING = "TRAILING"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class Position:
    trade_id: str
    symbol: str
    horizon: str
    state: TradeState
    created_date: str
    updated_date: str
    entry: float
    initial_stop: float
    stop: float
    target1: float
    target2: float
    quantity: float
    remaining_quantity: float
    realised_quantity: float = 0.0
    realised_pnl: float = 0.0
    last_price: float | None = None
    exit_price: float | None = None
    reason: str = "created"


def new_position(symbol: str, horizon: str, trade_date: str, entry: float, stop: float,
                 target1: float, target2: float, quantity: float = 1.0) -> Position:
    if not (stop < entry < target1 <= target2):
        raise ValueError("invalid long trade geometry")
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    return Position(
        trade_id=str(uuid4()), symbol=symbol, horizon=horizon, state=TradeState.WATCH,
        created_date=trade_date, updated_date=trade_date, entry=entry, initial_stop=stop, stop=stop,
        target1=target1, target2=target2, quantity=quantity,
        remaining_quantity=quantity,
    )


def transition(position: Position, event: str, trade_date: str, price: float | None = None,
               partial_fraction: float = 0.5, trailing_stop: float | None = None,
               reason: str | None = None) -> Position:
    event = event.upper()
    state = position.state

    if event == "QUALIFY" and state == TradeState.WATCH:
        return replace(position, state=TradeState.READY, updated_date=trade_date,
                       last_price=price, reason=reason or "qualification_confirmed")
    if event == "ENTER" and state == TradeState.READY:
        return replace(position, state=TradeState.OPEN, updated_date=trade_date,
                       last_price=price or position.entry, reason=reason or "entry_triggered")
    if event == "T1_HIT" and state == TradeState.OPEN:
        if not 0 < partial_fraction < 1:
            raise ValueError("partial_fraction must be between 0 and 1")
        sold = position.remaining_quantity * partial_fraction
        return replace(position, state=TradeState.PARTIAL, updated_date=trade_date,
                       remaining_quantity=position.remaining_quantity - sold,
                       realised_quantity=position.realised_quantity + sold,
                       realised_pnl=position.realised_pnl + sold * ((price or position.target1) - position.entry),
                       last_price=price or position.target1,
                       stop=max(position.stop, position.entry),
                       reason=reason or "target1_partial_exit")
    if event == "TRAIL" and state in {TradeState.OPEN, TradeState.PARTIAL, TradeState.TRAILING}:
        if trailing_stop is None or trailing_stop < position.stop:
            raise ValueError("trailing stop cannot move backward")
        return replace(position, state=TradeState.TRAILING, updated_date=trade_date,
                       stop=trailing_stop, last_price=price,
                       reason=reason or "trailing_stop_advanced")
    if event in {"STOP_HIT", "T2_HIT", "EXIT"} and state in {TradeState.OPEN, TradeState.PARTIAL, TradeState.TRAILING}:
        exit_price = price if price is not None else (position.stop if event == "STOP_HIT" else position.target2)
        sold = position.remaining_quantity
        return replace(position, state=TradeState.CLOSED, updated_date=trade_date,
                       realised_quantity=position.quantity, remaining_quantity=0.0,
                       realised_pnl=position.realised_pnl + sold * (exit_price - position.entry),
                       last_price=exit_price, exit_price=exit_price,
                       reason=reason or event.lower())
    if event == "CANCEL" and state in {TradeState.WATCH, TradeState.READY}:
        return replace(position, state=TradeState.CANCELLED, updated_date=trade_date,
                       last_price=price, reason=reason or "setup_invalidated_before_entry")
    if event == "MARK":
        return replace(position, updated_date=trade_date, last_price=price,
                       reason=reason or position.reason)
    raise ValueError(f"invalid transition: {state.value} + {event}")
