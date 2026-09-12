"""Headless-Chromium fetcher backed by Playwright, for pages where
availability is only rendered client-side via JavaScript.

The browser is launched lazily on first use and reused across calls;
call .close() when done to shut it down cleanly.
"""
from __future__ import annotations

from hutwatch.fetchers.base import FetchResult


class PlaywrightFetcher:
    def __init__(self, user_agent: str, timeout_seconds: float = 20.0) -> None:
        self._user_agent = user_agent
        self._timeout_ms = timeout_seconds * 1000
        self._playwright = None
        self._browser = None

    def _ensure_started(self) -> None:
        if self._browser is not None:
            return
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)

    def get(self, url: str) -> FetchResult:
        self._ensure_started()
        assert self._browser is not None
        context = self._browser.new_context(user_agent=self._user_agent)
        page = context.new_page()
        try:
            response = page.goto(url, timeout=self._timeout_ms, wait_until="networkidle")
            status_code = response.status if response is not None else None
            text = page.content()
            return FetchResult(url=url, status_code=status_code, text=text)
        except Exception as exc:  # noqa: BLE001 - surface any Playwright error uniformly
            return FetchResult(url=url, status_code=None, text="", error=str(exc))
        finally:
            context.close()

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
