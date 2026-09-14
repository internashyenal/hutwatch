"""Rifugio Averau provider (Bukly booking engine).

Data source
-----------
Rifugio Averau uses the "Bukly" hotel booking engine
(https://rifugioaverau.bukly.com/). The check-availability page for a given
stay is a plain, cookie-independent GET request of the form:

    GET /en-us/hotel/{checkin_iso}/{checkout_iso}/

e.g. https://rifugioaverau.bukly.com/en-us/hotel/2027-09-01/2027-09-02/

This was confirmed via a captured browser session (HAR): the site's own
"search" form POSTs to `/` and 302-redirects to exactly this URL pattern, and
the page itself requires no session-specific data to render - it is a public,
bookmarkable/shareable URL.

The page renders a single `<table>` "availability grid": a header row of 15
consecutive calendar days (month abbreviation + day-of-month + weekday, e.g.
`<span class="month">Sep</span><span class="day">01</span>`), followed by one
row per bookable room/rate ("B&B dormitory n.3", "2 beds B&B (room 4)",
"Double room B&B (room 5) Bunk bed", ...). Each row/day cell contains a
`<div>` whose class indicates that room's status for that specific day:

    s-open        - bookable
    s-closed      - not bookable (sold out for that date)
    s-restricted  - bookable in principle but blocked by a booking
                    restriction for the exact requested dates (most likely a
                    minimum-length-of-stay rule). We deliberately treat this
                    the same as "not bookable" for alerting purposes, since
                    hutwatch's target is a specific, exact night count and a
                    restricted cell means that specific request cannot
                    currently be completed - alerting on it would risk a
                    false positive that sends the user chasing a booking
                    they can't actually make.

Unlike Rifugio Lagazuoi's calendar (which exposes a literal per-day bunk-bed
count), Bukly's grid only exposes a per-room-type open/closed/restricted
status with no bed count. To fit hutwatch's generic `Availability.beds`
threshold model (`beds >= target.beds_required`), we map each row's label to
an approximate sleeping capacity:

    "<N> beds ..."   -> N
    "Double room ..." -> 2
    "Single ..."      -> 1
    anything else (e.g. whole-dormitory-room listings with no explicit count)
                      -> _UNSPECIFIED_CAPACITY, a conservative "large enough
                         for a small group" fallback, since these rows
                         represent an entire shared room being bookable as a
                         unit.

`Availability.beds` is then the *largest* capacity among currently `s-open`
rows for the requested check-in date (the single best-fitting bookable
option), not a sum across rows - a party books one room, not several.

We only ever issue GET requests against this calendar view, never against
the multi-step booking/payment flow.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from bs4 import BeautifulSoup, Tag

from hutwatch.fetchers.base import Fetcher
from hutwatch.providers.base import Availability, ProviderParseError

name = "averau"
booking_url = "https://rifugioaverau.bukly.com/"

_BASE_URL = "https://rifugioaverau.bukly.com"
_UNSPECIFIED_CAPACITY = 8  # fallback for whole-room/dormitory listings with no explicit bed count


def build_calendar_url(check_in: date, nights: int) -> str:
    checkout = check_in + timedelta(days=nights)
    return f"{_BASE_URL}/en-us/hotel/{check_in.isoformat()}/{checkout.isoformat()}/"


def _row_capacity(label: str) -> int:
    match = re.match(r"\s*(\d+)\s*beds?\b", label, re.IGNORECASE)
    if match:
        return int(match.group(1))
    lowered = label.lower()
    if "double" in lowered:
        return 2
    if "single" in lowered:
        return 1
    return _UNSPECIFIED_CAPACITY


def _find_date_column(table: Tag, check_in: date) -> int | None:
    """Return the 0-based index (within each row's per-day <td> cells,
    i.e. excluding the leading label cell) of the column matching check_in.
    """
    header_row = table.find("tr")
    if header_row is None:
        return None
    headers = header_row.find_all("th")
    target_month = check_in.strftime("%b")
    target_day = f"{check_in.day:02d}"
    # headers[0] is the blank corner cell; day columns start at index 1.
    for idx, th in enumerate(headers[1:]):
        month_span = th.find("span", class_="month")
        day_span = th.find("span", class_="day")
        if month_span is None or day_span is None:
            continue
        if month_span.get_text(strip=True) == target_month and day_span.get_text(strip=True) == target_day:
            return idx
    return None


def get_availability(fetcher: Fetcher, check_in: date, nights: int) -> Availability:
    url = build_calendar_url(check_in, nights)
    result = fetcher.get(url)
    if not result.ok:
        raise ProviderParseError(
            f"fetch failed for {url}: status={result.status_code} error={result.error}"
        )

    soup = BeautifulSoup(result.text, "html.parser")
    table = soup.find("table")
    if table is None:
        raise ProviderParseError("no availability table found on page; site structure may have changed")

    col_index = _find_date_column(table, check_in)
    if col_index is None:
        raise ProviderParseError(
            f"could not find a calendar column for {check_in.isoformat()} in the availability table"
        )

    rows = table.find_all("tr")[1:]  # skip header row
    if not rows:
        raise ProviderParseError("availability table had no room rows")

    best_beds: int | None = None
    best_label = "none"
    for row in rows:
        label_cell = row.find("td")
        if label_cell is None:
            continue
        label = label_cell.get_text(strip=True)
        day_cells = row.find_all("td")[1:]
        if col_index >= len(day_cells):
            continue
        status_div = day_cells[col_index].find("div")
        status = status_div.get("class", [None])[0] if status_div else None
        if status != "s-open":
            continue
        capacity = _row_capacity(label)
        if best_beds is None or capacity > best_beds:
            best_beds = capacity
            best_label = label

    if best_beds is None:
        return Availability(beds=0, room_type="none", raw=f"col={col_index}")
    return Availability(beds=best_beds, room_type=best_label, raw=f"col={col_index} label={best_label!r}")
