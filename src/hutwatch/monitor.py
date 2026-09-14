"""Single-check monitor logic: fetch -> parse -> log -> evaluate -> notify.

Kept separate from the polling loop (poller.py) so --once and --dry-run can
drive it directly without spinning up a scheduler.

A single check run iterates over every configured target (each an
independent single-night-or-more stay to watch) and evaluates them one at a
time, with their own alert arm/disarm and consecutive-failure state tracked
under that target's `label`.
"""
from __future__ import annotations

import logging
from datetime import date as _date
from datetime import datetime, timezone

from hutwatch.config import Config, TargetConfig
from hutwatch.fetchers.base import Fetcher
from hutwatch.notifiers.base import Notification, Notifier
from hutwatch.providers.base import Availability, Provider, ProviderParseError
from hutwatch.state import StateStore

logger = logging.getLogger(__name__)

_BROKEN_ARMED_KEY_PREFIX = "broken_alert_armed"


def _notify_all(notifiers: list[Notifier], notification: Notification) -> None:
    for notifier in notifiers:
        try:
            notifier.send(notification)
        except Exception:  # noqa: BLE001 - one notifier failing must not block others
            logger.exception("Notifier %r failed to send", type(notifier).__name__)


def _availability_message(config: Config, target: TargetConfig, availability: Availability) -> Notification:
    checkout_date = _date.fromordinal(target.check_in.toordinal() + target.nights)
    subject = f"[{target.label}] Bed available at {target.provider}: {availability.beds} beds"
    body = (
        f"{target.label}\n"
        f"{availability.beds} bed(s) available ({availability.room_type})\n"
        f"Check-in: {target.check_in.isoformat()}  Check-out: {checkout_date.isoformat()} "
        f"({target.nights} night(s))\n"
        f"Book here: {target.url}"
    )
    return Notification(subject=subject, body=body)


def _broken_message(config: Config, target: TargetConfig, reason: str, consecutive_failures: int) -> Notification:
    subject = f"hutwatch monitor is broken ({target.provider}: {target.label})"
    body = (
        f"{consecutive_failures} consecutive checks have failed for '{target.label}'.\n"
        f"Last error: {reason}\n"
        "The monitor cannot currently tell you about bed availability. Please investigate."
    )
    return Notification(subject=subject, body=body)


def run_once(
    config: Config,
    fetcher: Fetcher,
    providers: dict[str, Provider],
    state: StateStore,
    notifiers: list[Notifier],
) -> list[Availability | None]:
    """Run a single check against every configured target.

    `providers` maps each target's `provider` name to its loaded Provider
    module, so different targets can independently monitor different huts.

    Returns a list of results (parsed Availability, or None on failure) in
    the same order as `config.targets`.
    """
    return [
        _check_target(config, target, fetcher, providers[target.provider], state, notifiers)
        for target in config.targets
    ]


def _check_target(
    config: Config,
    target: TargetConfig,
    fetcher: Fetcher,
    provider: Provider,
    state: StateStore,
    notifiers: list[Notifier],
) -> Availability | None:
    broken_armed_key = f"{_BROKEN_ARMED_KEY_PREFIX}:{target.label}"
    try:
        availability = provider.get_availability(fetcher, target.check_in, target.nights)
    except ProviderParseError as exc:
        state.log_check(beds=None, room_type=None, http_status=None, error=str(exc), label=target.label)
        failures = state.record_failure(target.label)
        logger.warning("[%s] Check failed (%d consecutive): %s", target.label, failures, exc)
        if failures >= config.alerts.max_consecutive_failures:
            if state.get_value(broken_armed_key) != "0":
                _notify_all(notifiers, _broken_message(config, target, str(exc), failures))
                state.set_value(broken_armed_key, "0")
        return None

    state.log_check(
        beds=availability.beds,
        room_type=availability.room_type,
        http_status=200,
        error=None,
        label=target.label,
    )
    state.record_success(target.label)
    state.set_value(broken_armed_key, "1")  # re-arm broken-monitor alert for next failure streak

    if availability.beds is None:
        # Parser ran but couldn't determine a bed count: treat as a soft
        # failure for alerting purposes without polluting the hard-failure
        # counter used above (that one is reserved for fetch/parse exceptions).
        logger.warning(
            "[%s] Availability parsed but beds is None (room_type=%r)", target.label, availability.room_type
        )
        return availability

    if state.should_alert(availability.beds, target.beds_required, label=target.label):
        logger.info(
            "[%s] Threshold crossed: beds=%d >= required=%d",
            target.label,
            availability.beds,
            target.beds_required,
        )
        _notify_all(notifiers, _availability_message(config, target, availability))

    return availability


def run_dry_run(config: Config, notifiers: list[Notifier]) -> None:
    """Force a fake positive result for every target and send it through the
    notification path, without touching the real state machine (so it can be
    re-run freely).
    """
    for target in config.targets:
        fake = Availability(
            beds=target.beds_required,
            room_type="[DRY RUN] Dormitory (bunk beds)",
            raw="<dry-run, no real data fetched>",
        )
        notification = _availability_message(config, target, fake)
        notification.subject = "[DRY RUN] " + notification.subject
        _notify_all(notifiers, notification)


def maybe_send_heartbeat(config: Config, state: StateStore, notifiers: list[Notifier]) -> None:
    """Send at most one heartbeat per UTC calendar day, once the configured hour has passed."""
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    if now.hour < config.alerts.heartbeat_hour_utc:
        return
    if state.last_heartbeat_date() == today:
        return

    body_lines = ["hutwatch heartbeat: still running."]
    for target in config.targets:
        recent = state.recent_checks(limit=1, label=target.label)
        last = recent[0] if recent else None
        if last is not None:
            body_lines.append(
                f"[{target.label}] ({target.provider}) last check at {last.timestamp}: "
                f"beds={last.beds} room_type={last.room_type} error={last.error}"
            )
        else:
            body_lines.append(f"[{target.label}] no checks recorded yet.")

    _notify_all(notifiers, Notification(subject="hutwatch heartbeat", body="\n".join(body_lines)))
    state.set_last_heartbeat_date(today)
