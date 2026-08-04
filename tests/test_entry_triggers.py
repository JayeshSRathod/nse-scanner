from v2.entry_triggers import EntryTrigger, select_primary_trigger


def test_primary_trigger_prefers_qualified_pullback_over_breakout():
    triggers = (
        EntryTrigger("BREAKOUT", True, 95.0, ("breakout",), {}),
        EntryTrigger("QUALIFIED_PULLBACK", True, 72.0, ("pullback",), {}),
    )
    selected = select_primary_trigger(triggers)
    assert selected.name == "QUALIFIED_PULLBACK"


def test_primary_trigger_returns_no_trigger_when_none_actionable():
    triggers = (
        EntryTrigger("BREAKOUT", False, 100.0, ("not_actionable",), {}),
        EntryTrigger("NO_TRIGGER", False, 0.0, ("wait",), {}),
    )
    selected = select_primary_trigger(triggers)
    assert selected.name == "NO_TRIGGER"
    assert selected.actionable is False


def test_trigger_serialization_is_stable():
    trigger = EntryTrigger(
        name="TREND_CONTINUATION",
        actionable=True,
        score=78.0,
        reasons=("daily_and_weekly_trend_aligned",),
        metrics={"qualified_horizons": "3M,6M"},
    )
    payload = trigger.to_dict()
    assert payload["name"] == "TREND_CONTINUATION"
    assert payload["score"] == 78.0
    assert payload["metrics"]["qualified_horizons"] == "3M,6M"
