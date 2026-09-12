"""State-machine tests: alert only on a fresh below->at/above-threshold
transition, once per transition, re-arming when availability drops again.
"""
from __future__ import annotations

from hutwatch.state import StateStore


def make_store() -> StateStore:
    return StateStore(":memory:")


def test_no_alert_when_never_meeting_threshold():
    store = make_store()
    assert store.should_alert(0, threshold=2) is False
    assert store.should_alert(1, threshold=2) is False
    assert store.should_alert(0, threshold=2) is False


def test_alerts_once_on_crossing_then_suppresses_duplicates():
    store = make_store()
    assert store.should_alert(1, threshold=2) is False  # below threshold
    assert store.should_alert(2, threshold=2) is True  # crosses -> alert
    # Repeated positive checks must NOT alert again.
    assert store.should_alert(2, threshold=2) is False
    assert store.should_alert(3, threshold=2) is False
    assert store.should_alert(5, threshold=2) is False


def test_rearms_after_dropping_below_threshold():
    store = make_store()
    assert store.should_alert(2, threshold=2) is True
    assert store.should_alert(2, threshold=2) is False
    # Drops back below threshold: re-arms.
    assert store.should_alert(0, threshold=2) is False
    assert store.should_alert(1, threshold=2) is False
    # Crosses again: alerts again exactly once.
    assert store.should_alert(2, threshold=2) is True
    assert store.should_alert(2, threshold=2) is False


def test_none_beds_treated_as_below_threshold_and_rearms():
    store = make_store()
    assert store.should_alert(2, threshold=2) is True
    # A parse hiccup returning None should not itself alert, and should
    # re-arm (treated conservatively as "not confirmed available").
    assert store.should_alert(None, threshold=2) is False
    assert store.should_alert(2, threshold=2) is True


def test_repeated_many_positive_checks_alert_exactly_once():
    """Regression test: N consecutive positive checks must produce exactly one alert."""
    store = make_store()
    alerts = [store.should_alert(4, threshold=2) for _ in range(50)]
    assert alerts.count(True) == 1
    assert alerts[0] is True
