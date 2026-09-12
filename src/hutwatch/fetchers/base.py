"""Fetcher interface: interchangeable transport for retrieving a URL's HTML.

Two implementations are provided:
- HttpxFetcher: plain HTTP via httpx (fast, no browser required).
- PlaywrightFetcher: headless Chromium via Playwright, for pages that only
  render availability client-side via JavaScript.

Both expose the same `.get(url) -> FetchResult` interface so providers and the
monitor loop never need to know which transport is in use.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class FetchResult:
    url: str
    status_code: int | None
    text: str
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.status_code is not None and 200 <= self.status_code < 300


class Fetcher(Protocol):
    def get(self, url: str) -> FetchResult:
        """Fetch a URL and return its rendered/raw HTML text."""
        ...

    def close(self) -> None:
        """Release any resources (HTTP client, browser process, etc.)."""
        ...
