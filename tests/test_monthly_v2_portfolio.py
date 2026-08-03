from v2.horizon_promotion import PromotionDecision
from v2.monthly_portfolio import render_monthly_portfolio_message
from v2.portfolio_performance import PortfolioSnapshot


def test_monthly_message_labels_model_pnl_and_promotion():
    snapshot = PortfolioSnapshot("2026-08-31", 300000, 60000, 64000, 2500, 1500, 4000, 1.3333, 3000, 800, 1, 0)
    decision = PromotionDecision("id", "ABC", "SWING_1_3M", "POSITIONAL_3_6M", "PROMOTE", 24, 1.2,
                                 True, True, True, False, False, ("all_carry_forward_rules_passed",))
    message = render_monthly_portfolio_message("2026-08-31", snapshot, [decision])
    assert "Model portfolio - not broker-account P&L" in message
    assert "ABC" in message and "PROMOTE -> Positional (3-6M)" in message
    assert "never widens a stop" in message
