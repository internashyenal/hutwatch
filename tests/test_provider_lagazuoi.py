from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from hutwatch.fetchers.base import FetchResult
from hutwatch.providers import lagazuoi
from hutwatch.providers.base import ProviderParseError

FIXTURES = Path(__file__).parent / "fixtures"


class FakeFetcher:
    """Returns fixed HTML regardless of URL, for testing the parser in isolation."""

    def __init__(self, html: str, status_code: int = 200) -> None:
        self._html = html
        self._status_code = status_code

    def get(self, url: str) -> FetchResult:
        return FetchResult(url=url, status_code=self._status_code, text=self._html)

    def close(self) -> None:
        pass


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_month_offset_matches_observed_values():
    # Empirically confirmed: prm=11 -> December 2026, prm=20 -> September 2027.
    assert lagazuoi._month_offset(date(2026, 12, 22)) == 11
    assert lagazuoi._month_offset(date(2027, 9, 1)) == 20


def test_available_day_parses_dorm_beds_and_room_type():
    fetcher = FakeFetcher(_load_fixture("lagazuoi_available.html"))
    availability = lagazuoi.get_availability(fetcher, date(2026, 12, 22), nights=1)

    assert availability.beds == 13
    assert availability.room_type == "Dormitory (bunk beds)"
    assert "giorno-22" in availability.raw


def test_unavailable_day_parses_zero_beds():
    fetcher = FakeFetcher(_load_fixture("lagazuoi_unavailable.html"))
    availability = lagazuoi.get_availability(fetcher, date(2027, 9, 1), nights=1)

    assert availability.beds == 0
    assert availability.room_type == "none"


def test_broken_page_raises_parse_error():
    fetcher = FakeFetcher(_load_fixture("lagazuoi_broken.html"))
    with pytest.raises(ProviderParseError):
        lagazuoi.get_availability(fetcher, date(2027, 9, 1), nights=1)


def test_missing_day_in_valid_table_raises_parse_error():
    # lagazuoi_unavailable.html's September 2027 grid only goes up to day 12.
    fetcher = FakeFetcher(_load_fixture("lagazuoi_unavailable.html"))
    with pytest.raises(ProviderParseError):
        lagazuoi.get_availability(fetcher, date(2027, 9, 25), nights=1)


def test_http_error_raises_parse_error():
    fetcher = FakeFetcher(_load_fixture("lagazuoi_available.html"), status_code=500)
    with pytest.raises(ProviderParseError):
        lagazuoi.get_availability(fetcher, date(2026, 12, 22), nights=1)
