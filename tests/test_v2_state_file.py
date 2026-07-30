from __future__ import annotations

from v2.lifecycle import new_position, transition
from v2.portfolio_store import PortfolioStore
from v2.state_file import export_state_file, restore_state_file


def test_state_file_round_trip_preserves_position_pnl(tmp_path):
    first_db = tmp_path / "first.db"
    store = PortfolioStore(first_db)
    store.initialize()
    position = new_position("ABC", "SWING_1_3M", "2026-08-03", 100, 95, 110, 120, 10)
    position = transition(position, "QUALIFY", "2026-08-03", price=99)
    position = transition(position, "ENTER", "2026-08-03", price=100)
    position = transition(position, "T1_HIT", "2026-08-03", price=110)
    store.save_position(position, "T1_HIT")
    state_path = export_state_file(first_db, tmp_path / "v2_portfolio_state.json")
    second_db = tmp_path / "second.db"
    assert restore_state_file(second_db, state_path)
    restored = PortfolioStore(second_db).get_position(position.trade_id)
    assert restored is not None
    assert restored.realised_pnl == 50
    assert restored.remaining_quantity == 5
