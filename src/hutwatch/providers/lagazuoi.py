"""Rifugio Lagazuoi provider.

Data source
-----------
The hut's "Available beds in real time" calendar
(https://rifugiolagazuoi.com/EN/disponibilita.php) is server-rendered HTML
and requires no JavaScript. Each month is requested via:

    GET disponibilita.php?prm={offset}&chm=1

where `offset` is a stateless, cookie-free integer month index:

    offset = (year - _EPOCH_YEAR) * 12 + (month - 1)

This was confirmed empirically: offset=11 rendered "December 2026" and
offset=20 rendered "September 2027" (with _EPOCH_YEAR=2026, i.e. Jan 2026 = 0).
`chm=1` appears to just be a required direction flag; it does not need to
match the actual navigation direction to get a correct result.

Each calendar day is a <td> with class "chiuso" (not available, grey) or
"libero" (available, green). Available days additionally link
(`data-open="giorno-N"`) to a sibling `<div id="giorno-N">` containing one
"dettagli" block per room category plus one dormitory line of the form:

    Dormitories with bunk beds n. <N> beds available

We treat that dormitory bed count as the monitored "beds" value, since that is
the literal number of individually-bookable bunk beds left for that date (as
opposed to private rooms, which are booked as a whole unit). This matches the
user's real scenario: "Only 1 [dormitory bunk bed] is currently available."

We deliberately only ever issue GET requests against this calendar view. We
never POST to the booking search/reservation endpoints, per the read-only,
no-booking requirement.
"""
from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup, Tag

from hutwatch.fetchers.base import Fetcher
from hutwatch.providers.base import Availability, ProviderParseError

name = "lagazuoi"
booking_url = "https://rifugiolagazuoi.com/EN/disponibilita.php"

_CALENDAR_URL = "https://rifugiolagazuoi.com/EN/disponibilita.php"
_EPOCH_YEAR = 2026  # offset=0 corresponds to January 2026 (empirically derived, see module docstring)

_DORM_RE = re.compile(r"n\.\s*(\d+)\s*beds available", re.IGNORECASE)
_ROOM_RE = re.compile(r"n\.\s*(\d+)\s*(.+)", re.IGNORECASE)


def _month_offset(check_in: date) -> int:
    return (check_in.year - _EPOCH_YEAR) * 12 + (check_in.month - 1)


def build_calendar_url(check_in: date) -> str:
    return f"{_CALENDAR_URL}?prm={_month_offset(check_in)}&chm=1"


def _find_day_cell(soup: BeautifulSoup, day: int) -> Tag | None:
    """Find the <td class="libero|chiuso"> for the given day-of-month.

    The table has no per-cell date attributes, only the visible day-number
    text, so we match <td> elements whose class is libero/chiuso and whose
    stripped text equals the target day number exactly (avoiding accidental
    substring matches like "1" inside "12").
    """
    for td in soup.find_all("td", class_=("libero", "chiuso")):
        text = td.get_text(strip=True)
        if text == str(day):
            return td
    return None


def _parse_detail_div(detail_div: Tag) -> tuple[int | None, str]:
    """Parse a giorno-N detail div into (dorm_beds, room_type_summary)."""
    dettagli_blocks = detail_div.find_all("div", class_="dettagli")
    if not dettagli_blocks:
        raise ProviderParseError("libero day cell had no 'dettagli' blocks in its detail div")

    dorm_beds: int | None = None
    room_labels: list[str] = []

    for block in dettagli_blocks:
        block_text = " ".join(block.get_text(" ", strip=True).split())
        dorm_match = _DORM_RE.search(block_text)
        if dorm_match:
            dorm_beds = int(dorm_match.group(1))
            continue
        room_match = _ROOM_RE.match(block_text)
        if room_match:
            count = room_match.group(1)
            label = room_match.group(2).strip()
            room_labels.append(f"{label} (x{count})")

    if dorm_beds is not None:
        room_type = "Dormitory (bunk beds)"
    elif room_labels:
        room_type = room_labels[0]
    else:
        room_type = "unknown"

    return dorm_beds, room_type


def get_availability(fetcher: Fetcher, check_in: date, nights: int) -> Availability:
    url = build_calendar_url(check_in)
    result = fetcher.get(url)
    if not result.ok:
        raise ProviderParseError(
            f"fetch failed for {url}: status={result.status_code} error={result.error}"
        )

    soup = BeautifulSoup(result.text, "html.parser")

    table = soup.find("table", id="TabDisp")
    if table is None:
        raise ProviderParseError("calendar table #TabDisp not found; page layout may have changed")

    day_cell = _find_day_cell(soup, check_in.day)
    if day_cell is None:
        raise ProviderParseError(
            f"no day cell found for day={check_in.day} in calendar for {check_in.isoformat()}"
        )

    css_classes = day_cell.get("class") or []

    if "chiuso" in css_classes:
        return Availability(beds=0, room_type="none", raw=str(day_cell))

    if "libero" not in css_classes:
        raise ProviderParseError(f"unrecognized day cell classes: {css_classes!r}")

    link = day_cell.find("a", attrs={"data-open": True})
    if link is None:
        raise ProviderParseError("'libero' day cell had no data-open link to its detail div")
    detail_id = link["data-open"]

    detail_div = soup.find("div", id=detail_id)
    if detail_div is None:
        raise ProviderParseError(f"detail div #{detail_id} not found for libero day")

    dorm_beds, room_type = _parse_detail_div(detail_div)
    raw = str(day_cell) + str(detail_div)
    return Availability(beds=dorm_beds, room_type=room_type, raw=raw)
