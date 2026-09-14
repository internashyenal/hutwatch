"""Renders a static, read-only HTML status page from the state database.

Intended for publishing (e.g. via GitHub Pages) so status can be checked from
a browser without exposing the SQLite file or running a live server. Pure
stdlib - no template engine dependency.
"""
from __future__ import annotations

import html
from datetime import date as _date
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from hutwatch.config import Config, TargetConfig
from hutwatch.state import StateStore

_MELBOURNE_TZ = ZoneInfo("Australia/Melbourne")


def _to_melbourne(timestamp: str) -> str:
    """Formats a stored UTC ISO timestamp string as local Melbourne time."""
    try:
        dt = datetime.fromisoformat(timestamp)
    except ValueError:
        return timestamp
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_MELBOURNE_TZ).strftime("%Y-%m-%d %H:%M %Z")

_STYLE = """
body { font-family: system-ui, sans-serif; max-width: 52rem; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }
h1 { font-size: 1.3rem; }
h2 { font-size: 1.05rem; margin-top: 2rem; }
.badge { display: inline-block; padding: 0.15rem 0.6rem; border-radius: 999px; font-weight: 600; font-size: 0.85rem; white-space: nowrap; }
.badge.ok { background: #d6f5d6; color: #1a5c1a; }
.badge.none { background: #eee; color: #555; }
.badge.error { background: #fddede; color: #8a1c1c; }
table { border-collapse: collapse; width: 100%; margin-top: 1rem; font-size: 0.9rem; }
th, td { text-align: left; padding: 0.5rem 0.7rem; border-bottom: 1px solid #ddd; }
thead th { border-bottom: 2px solid #999; }
tr:hover td { background: #fafafa; }
.meta { color: #666; font-size: 0.85rem; margin-top: 1.5rem; }
a.book { font-weight: 600; }
details { margin-top: 0.5rem; }
summary { cursor: pointer; color: #555; }
"""


def _badge(beds: int | None, error: str | None) -> str:
    if error:
        return '<span class="badge error">check failed</span>'
    if beds is None:
        return '<span class="badge none">unknown</span>'
    if beds > 0:
        return f'<span class="badge ok">{beds} available</span>'
    return '<span class="badge none">0 available</span>'


def _history_rows(state: StateStore, target: TargetConfig, limit: int) -> str:
    records = state.recent_checks(limit=limit, label=target.label)
    if not records:
        return '<tr><td colspan="5">No checks logged yet.</td></tr>'
    rows = []
    for r in records:
        rows.append(
            "<tr>"
            f"<td>{html.escape(_to_melbourne(r.timestamp))}</td>"
            f"<td>{_badge(r.beds, r.error)}</td>"
            f"<td>{html.escape(r.room_type or '-')}</td>"
            f"<td>{r.http_status if r.http_status is not None else '-'}</td>"
            f"<td>{html.escape(r.error or '-')}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_status_html(config: Config, state: StateStore, limit: int = 20) -> str:
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    summary_rows = []
    history_sections = []
    for target in config.targets:
        checkout = _date.fromordinal(target.check_in.toordinal() + target.nights)
        latest = state.recent_checks(limit=1, label=target.label)
        last = latest[0] if latest else None
        badge = _badge(last.beds, last.error) if last else '<span class="badge none">no data yet</span>'
        last_checked = html.escape(_to_melbourne(last.timestamp)) if last else "-"

        summary_rows.append(
            "<tr>"
            f"<td>{html.escape(target.label)}</td>"
            f'<td><a href="{html.escape(target.url)}">{html.escape(target.provider)}</a></td>'
            f"<td>{target.check_in.isoformat()} &rarr; {checkout.isoformat()}</td>"
            f"<td>{target.nights}</td>"
            f"<td>{target.beds_required}</td>"
            f"<td>{badge}</td>"
            f"<td>{last_checked}</td>"
            f"<td>{state.get_consecutive_failures(target.label)}</td>"
            "</tr>"
        )

        history_sections.append(
            f"""<details>
<summary>{html.escape(target.label)} ({html.escape(target.provider)}) &mdash; recent checks</summary>
<table>
<thead><tr><th>Timestamp (Melbourne)</th><th>Result</th><th>Room type</th><th>HTTP</th><th>Error</th></tr></thead>
<tbody>
{_history_rows(state, target, limit)}
</tbody>
</table>
</details>"""
        )

    summary_rows_html = "\n".join(summary_rows) if summary_rows else '<tr><td colspan="8">No targets configured.</td></tr>'
    history_html = "\n".join(history_sections)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="600">
<title>hutwatch status</title>
<style>{_STYLE}</style>
</head>
<body>
<h1>hutwatch availability monitor</h1>

<h2>Watched dates</h2>
<table>
<thead>
<tr>
  <th>Label</th>
  <th>Hut</th>
  <th>Dates</th>
  <th>Nights</th>
  <th>Beds needed</th>
  <th>Latest result</th>
  <th>Last checked (Melbourne)</th>
  <th>Consec. failures</th>
</tr>
</thead>
<tbody>
{summary_rows_html}
</tbody>
</table>

<h2>Check history</h2>
{history_html}

<p class="meta">Page generated: {generated_at}</p>
<p class="meta">Read-only monitor. This page does not book anything for you.</p>
</body>
</html>
"""

