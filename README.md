# hutwatch

Read-only availability monitor for Rifugio Lagazuoi. Polls the hut's booking
calendar, and sends a phone notification the moment enough beds become
available for your dates — so you can go book them yourself.

## What it does (and does not do)

- Polls `disponibilita.php` (the calendar widget behind the public booking
  page) for one or more configured single-night stays (each its own date and
  required bed count), and extracts the number of dormitory bunk beds
  available on each date.
- Alerts you (via ntfy.sh) the moment any watched date transitions from
  below its required bed count to at-or-above it. Each watched date is
  tracked independently — it will not alert you again for the same
  transition, and re-arms itself if availability later drops back below the
  threshold.
- Sends a "monitor is broken" alert if the page structure changes and the
  parser can no longer make sense of it, or after several consecutive fetch
  failures (tracked per watched date). Sends a daily heartbeat so you know
  it's still running.
- Logs every single check (timestamp, beds found, HTTP status, error) per
  watched date to a local SQLite database.

**Non-goals**: this tool never completes a booking, logs in, submits any
form, or attempts to solve a CAPTCHA. It only reads a public calendar page.
You are responsible for actually booking once notified.

### A note on "beds"

The hut's calendar shows both private rooms (booked as a whole unit) and a
dormitory (individually bookable bunk beds). `hutwatch` treats **dormitory
bunk beds** as the "beds" metric, since that's what lets N unrelated people
each grab a spot. Private room availability is *not* currently counted
toward the threshold (see `providers/lagazuoi.py` for the parsing details).

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) for dependency management
- On Windows, if you want to create the venv with `uv venv` and let uv pick a
  Python automatically, prefer an already-released stable version (e.g.
  `uv venv --python 3.12`) — very new versions may not yet have prebuilt
  wheels for the Playwright dependency, `greenlet`.

## Setup

```bash
git clone <this-repo>
cd hut-watch
uv venv --python 3.12
uv sync --extra dev
```

If you plan to use the Playwright fetch engine (`fetch.engine = "playwright"`
in `config.toml`), also install its browser binary once:

```bash
uv run playwright install chromium
```

Copy the secrets template and fill in real values:

```bash
cp .env.example .env
```

`.env` holds only secrets (ntfy topic, SMTP credentials) referenced by
environment-variable name from `config.toml` — never commit real values.

Review and edit `config.toml` for your target dates, bed count, poll
interval, and which notifiers are enabled.

Each `[[targets]]` entry in `config.toml` is an independent single night to
watch (its own `check_in` date, `nights` — normally `1` — and
`beds_required`). Add as many as you like to scan a window of candidate
dates; each gets its own alert arm/disarm state, so a hit on one date never
suppresses alerts for another.

## Usage

Run a single check and exit (useful for cron / CI):

```bash
uv run hutwatch --once
```

Run continuously, polling on the configured interval (default 20 min ± 5,
with exponential backoff on errors and a hard floor of one request per 10
minutes):

```bash
uv run hutwatch
```

Send a fake positive-availability notification to verify your notifier setup
end-to-end, without touching state or making a real availability decision:

```bash
uv run hutwatch --dry-run
```

Use `-v`/`--verbose` for debug logging, and `--config <path>` to point at a
different config file.

View the most recent logged check(s) straight from the state database
without performing a live fetch:

```bash
uv run hutwatch --status       # most recent check
uv run hutwatch --status 10    # 10 most recent checks
```

Render a simple, read-only HTML status page from the state database (see
[GitHub Pages](#github-pages-status-page-optional) below for hosting it on
the web):

```bash
uv run hutwatch --render-status public/index.html
```

On startup, `hutwatch` checks the target site's `robots.txt` and refuses to
run if disallowed for its User-Agent (which includes a contact email from
`config.toml`).

## Tests

```bash
uv run pytest -v
```

Includes parser tests against saved HTML fixtures and a state-machine test
proving no duplicate alerts are sent across repeated positive checks.

## Deployment options

### systemd (persistent host)

See [systemd/hutwatch.service](systemd/hutwatch.service). Edit the paths and
`WorkingDirectory`, then:

```bash
sudo cp systemd/hutwatch.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hutwatch
```

### Docker

```bash
docker build -t hutwatch .
docker run -d --name hutwatch \
  --env-file .env \
  -v $(pwd)/config.toml:/app/config.toml:ro \
  -v hutwatch-data:/app/data \
  hutwatch
```

### GitHub Actions (zero-infra alternative)

[.github/workflows/check.yml](.github/workflows/check.yml) runs `hutwatch
--once` on a cron schedule instead of a long-lived process. It caches the
SQLite state database between runs (via `actions/cache`) so the
alert-transition logic still works across ephemeral runs. Configure repo
secrets matching the env var names in `.env.example`.

#### GitHub Pages status page (optional)

The same workflow renders a static HTML status page
(`hutwatch --render-status public/index.html`) after every check and
publishes it to GitHub Pages, so you can check availability from any
browser without exposing the SQLite database or running a server. To enable
it:

1. In the repo, go to **Settings → Pages** and set **Source** to
   "GitHub Actions".
2. Push the workflow (it already requests the `pages: write` /
   `id-token: write` permissions it needs).
3. After the first run, the page is published at
   `https://<you>.github.io/<repo>/`.

The page only shows non-sensitive info (check-in date, bed counts, room
type, booking link) — no secrets or raw HTML from the target site.

## Roadmap / TODO

- **Email (SMTP) notifications**: `notifiers/smtp.py` and the
  `[notifiers.smtp]` config section already exist, but SMTP is not yet
  enabled or configured with real credentials — currently only `ntfy` is
  active. To enable: add `"smtp"` to `notifiers.enabled` in `config.toml`
  and fill in real `SMTP_*` values in `.env`.

