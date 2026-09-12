"""Integration-level tests for hutwatch.monitor: exercise the full
fetch -> parse -> log -> transition -> notify pipeline with fake providers,
fetchers, and notifiers (no real network calls).
"""
from __future__ import annotations

from datetime import date

from hutwatch.config import (
    AlertsConfig,
    Config,
    FetchConfig,
    HutConfig,
    NotifiersConfig,
    PollingConfig,
    StateConfig,
    TargetConfig,
)
from hutwatch.monitor import run_once
from hutwatch.notifiers.base import Notification
from hutwatch.providers.base import Availability, ProviderParseError
from hutwatch.state import StateStore


class FakeProvider:
    name = "fake"
    booking_url = "https://example.invalid/book"

    def __init__(self, results):
        self._results = list(results)

    def get_availability(self, fetcher, check_in, nights):
        item = self._results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeNotifier:
    def __init__(self):
        self.sent: list[Notification] = []

    def send(self, notification: Notification) -> None:
        self.sent.append(notification)


def make_config(beds_required: int = 2, max_consecutive_failures: int = 3) -> Config:
    return Config(
        hut=HutConfig(provider="fake", url="https://example.invalid/disponibilita.php"),
        targets=[
            TargetConfig(
                label="test-target",
                check_in=date(2027, 9, 1),
                nights=1,
                beds_required=beds_required,
            )
        ],
        fetch=FetchConfig(engine="httpx", timeout_seconds=10, contact_email="test@example.com"),
        polling=PollingConfig(
            interval_minutes=20,
            jitter_minutes=5,
            min_interval_minutes=10,
            backoff_initial_seconds=30,
            backoff_max_seconds=3600,
            backoff_multiplier=2.0,
        ),
        alerts=AlertsConfig(max_consecutive_failures=max_consecutive_failures, heartbeat_hour_utc=6),
        state=StateConfig(db_path=":memory:"),
        notifiers=NotifiersConfig(enabled=[]),
    )


def test_repeated_positive_checks_alert_exactly_once():
    config = make_config(beds_required=2)
    state = StateStore(":memory:")
    notifier = FakeNotifier()
    provider = FakeProvider(
        [
            Availability(beds=1, room_type="Dormitory (bunk beds)", raw=""),
            Availability(beds=2, room_type="Dormitory (bunk beds)", raw=""),
            Availability(beds=2, room_type="Dormitory (bunk beds)", raw=""),
            Availability(beds=3, room_type="Dormitory (bunk beds)", raw=""),
        ]
    )

    for _ in range(4):
        run_once(config, fetcher=object(), provider=provider, state=state, notifiers=[notifier])

    assert len(notifier.sent) == 1
    assert "2" in notifier.sent[0].subject or "beds" in notifier.sent[0].subject


def test_broken_alert_fires_after_max_consecutive_failures():
    config = make_config(max_consecutive_failures=3)
    state = StateStore(":memory:")
    notifier = FakeNotifier()
    provider = FakeProvider(
        [
            ProviderParseError("boom 1"),
            ProviderParseError("boom 2"),
            ProviderParseError("boom 3"),
        ]
    )

    for _ in range(3):
        run_once(config, fetcher=object(), provider=provider, state=state, notifiers=[notifier])

    assert len(notifier.sent) == 1
    assert "broken" in notifier.sent[0].subject.lower()


def test_broken_alert_does_not_repeat_every_cycle_once_fired():
    config = make_config(max_consecutive_failures=2)
    state = StateStore(":memory:")
    notifier = FakeNotifier()
    provider = FakeProvider(
        [
            ProviderParseError("boom 1"),
            ProviderParseError("boom 2"),
            ProviderParseError("boom 3"),
            ProviderParseError("boom 4"),
        ]
    )

    for _ in range(4):
        run_once(config, fetcher=object(), provider=provider, state=state, notifiers=[notifier])

    assert len(notifier.sent) == 1


def test_recovery_then_new_failure_streak_alerts_again():
    config = make_config(max_consecutive_failures=2)
    state = StateStore(":memory:")
    notifier = FakeNotifier()
    provider = FakeProvider(
        [
            ProviderParseError("boom 1"),
            ProviderParseError("boom 2"),  # 1st broken alert
            Availability(beds=0, room_type="none", raw=""),  # recovers, resets failure count
            ProviderParseError("boom 3"),
            ProviderParseError("boom 4"),  # 2nd broken alert
        ]
    )

    for _ in range(5):
        run_once(config, fetcher=object(), provider=provider, state=state, notifiers=[notifier])

    assert len(notifier.sent) == 2
