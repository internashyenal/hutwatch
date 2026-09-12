"""Provider-agnostic types. All site-specific scraping logic lives in
hutwatch.providers.<site>; everything else in the codebase only depends on
this module's Availability/Provider/ProviderParseError contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from hutwatch.fetchers.base import Fetcher


@dataclass
class Availability:
    beds: int | None
    room_type: str
    raw: str


class ProviderParseError(Exception):
    """Raised when the page structure is unrecognizable (likely a site redesign).

    This is distinct from a "0 beds available" result: a well-formed page that
    clearly says "not available" should return Availability(beds=0, ...), not
    raise. This exception is reserved for cases where the parser cannot make
    sense of the page at all.
    """


class Provider(Protocol):
    name: str
    booking_url: str

    def get_availability(self, fetcher: Fetcher, check_in: date, nights: int) -> Availability:
        """Fetch and parse availability for the given check-in date and nights.

        Must not submit any form, log in, or otherwise mutate state on the
        target site. Read-only GET requests only.
        """
        ...
