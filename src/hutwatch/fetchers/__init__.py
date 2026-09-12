from __future__ import annotations

from hutwatch.config import FetchConfig
from hutwatch.fetchers.base import Fetcher


def build_fetcher(fetch_config: FetchConfig) -> Fetcher:
    """Instantiate the configured Fetcher implementation."""
    user_agent = (
        f"hutwatch/0.1 (+read-only availability monitor; contact: {fetch_config.contact_email})"
    )
    if fetch_config.engine == "httpx":
        from hutwatch.fetchers.httpx_fetcher import HttpxFetcher

        return HttpxFetcher(user_agent=user_agent, timeout_seconds=fetch_config.timeout_seconds)
    elif fetch_config.engine == "playwright":
        from hutwatch.fetchers.playwright_fetcher import PlaywrightFetcher

        return PlaywrightFetcher(user_agent=user_agent, timeout_seconds=fetch_config.timeout_seconds)
    else:
        raise ValueError(f"Unknown fetch engine: {fetch_config.engine!r}")
