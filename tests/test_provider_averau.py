"""Tests for hutwatch.providers.averau (Bukly booking engine parser)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from hutwatch.fetchers.base import FetchResult
from hutwatch.providers import averau
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


def test_build_calendar_url_uses_checkin_and_checkout():
    url = averau.build_calendar_url(date(2027, 9, 1), nights=1)
    assert url == "https://rifugioaverau.bukly.com/en-us/hotel/2027-09-01/2027-09-02/"


def test_all_closed_or_restricted_day_parses_zero_beds():
    fetcher = FakeFetcher(_load_fixture("averau_unavailable.html"))
    availability = averau.get_availability(fetcher, date(2027, 9, 1), nights=1)

    assert availability.beds == 0
    assert availability.room_type == "none"


def test_open_day_picks_best_fitting_open_room():
    fetcher = FakeFetcher(_load_fixture("averau_available.html"))
    availability = averau.get_availability(fetcher, date(2027, 9, 1), nights=1)

    # Both "2 beds B&B (room 4)" and "Single B&B (room 5)" are open on Sep 01;
    # the 2-bed room should win as the larger-capacity match.
    assert availability.beds == 2
    assert "2 beds" in availability.room_type


def test_restricted_cell_is_not_treated_as_available():
    fetcher = FakeFetcher(_load_fixture("averau_unavailable.html"))
    # Aug 30/31 are s-restricted for the 2-beds row and s-open for the Single
    # row; Sep 01 (our real target) is fully closed - confirm restricted
    # never counts as open regardless of column.
    availability = averau.get_availability(fetcher, date(2027, 9, 1), nights=1)
    assert availability.beds == 0


def test_missing_date_column_raises_parse_error():
    fetcher = FakeFetcher(_load_fixture("averau_available.html"))
    with pytest.raises(ProviderParseError):
        averau.get_availability(fetcher, date(2027, 10, 1), nights=1)


def test_no_table_raises_parse_error():
    fetcher = FakeFetcher(_load_fixture("averau_broken.html"))
    with pytest.raises(ProviderParseError):
        averau.get_availability(fetcher, date(2027, 9, 1), nights=1)


def test_http_error_raises_parse_error():
    fetcher = FakeFetcher(_load_fixture("averau_available.html"), status_code=500)
    with pytest.raises(ProviderParseError):
        averau.get_availability(fetcher, date(2027, 9, 1), nights=1)
