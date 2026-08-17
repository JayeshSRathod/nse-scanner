from v2.fundamentals import FundamentalSnapshot, evaluate_fundamentals
from v2.progression import ProgressionStage, next_holding_stage


def test_strong_fundamentals_pass():
    gate = evaluate_fundamentals(FundamentalSnapshot(
        "ABC", "2026-06-30", 12, 18, 17, 0.4, True, 0, False,
    ))
    assert gate.passed
    assert gate.score == 6


def test_governance_flag_fails_even_with_strong_numbers():
    gate = evaluate_fundamentals(FundamentalSnapshot(
        "ABC", "2026-06-30", 12, 18, 17, 0.4, True, 0, True,
    ))
    assert not gate.passed
    assert "governance_risk_flag" in gate.reasons_against


def test_6m_promotion_requires_explicit_fundamental_pass():
    blocked = next_holding_stage(
        "QUALIFIED_3M", {"6M": "QUALIFIED"}, 65,
        trend_intact=True, fundamentals_passed=None,
    )
    assert blocked.stage == ProgressionStage.QUALIFIED_3M
    promoted = next_holding_stage(
        "QUALIFIED_3M", {"6M": "QUALIFIED"}, 65,
        trend_intact=True, fundamentals_passed=True,
    )
    assert promoted.stage == ProgressionStage.QUALIFIED_6M
