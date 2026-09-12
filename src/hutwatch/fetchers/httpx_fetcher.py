"""Plain HTTP fetcher backed by httpx."""
from __future__ import annotations

import httpx

from hutwatch.fetchers.base import FetchResult


class HttpxFetcher:
    def __init__(self, user_agent: str, timeout_seconds: float = 20.0) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=timeout_seconds,
            follow_redirects=True,
        )

    def get(self, url: str) -> FetchResult:
        try:
            resp = self._client.get(url)
        except httpx.HTTPError as exc:
            return FetchResult(url=url, status_code=None, text="", error=str(exc))
        return FetchResult(url=url, status_code=resp.status_code, text=resp.text)

    def close(self) -> None:
        self._client.close()
