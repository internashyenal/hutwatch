"""Polling loop: configurable interval with jitter, exponential backoff on
failure, and a hard floor of one request per `min_interval_minutes`.
"""
from __future__ import annotations

import logging
import random
import time

from hutwatch.config import Config
from hutwatch.fetchers.base import Fetcher
from hutwatch.monitor import maybe_send_heartbeat, run_once
from hutwatch.notifiers.base import Notifier
from hutwatch.providers.base import Provider
from hutwatch.state import StateStore

logger = logging.getLogger(__name__)


def _next_interval_seconds(config: Config, consecutive_failures: int) -> float:
    floor_seconds = config.polling.min_interval_minutes * 60

    if consecutive_failures > 0:
        backoff = config.polling.backoff_initial_seconds * (
            config.polling.backoff_multiplier ** (consecutive_failures - 1)
        )
        backoff = min(backoff, config.polling.backoff_max_seconds)
        return max(backoff, floor_seconds)

    base_minutes = config.polling.interval_minutes
    jitter_minutes = random.uniform(-config.polling.jitter_minutes, config.polling.jitter_minutes)
    interval_seconds = (base_minutes + jitter_minutes) * 60
    return max(interval_seconds, floor_seconds)


def run_forever(
    config: Config,
    fetcher: Fetcher,
    provider: Provider,
    state: StateStore,
    notifiers: list[Notifier],
) -> None:
    logger.info("Starting hutwatch poll loop for provider=%s", config.hut.provider)
    while True:
        run_once(config, fetcher, provider, state, notifiers)
        maybe_send_heartbeat(config, state, notifiers)

        failures = max((state.get_consecutive_failures(t.label) for t in config.targets), default=0)
        sleep_seconds = _next_interval_seconds(config, failures)
        logger.info("Sleeping %.0fs (max consecutive_failures=%d)", sleep_seconds, failures)
        time.sleep(sleep_seconds)
