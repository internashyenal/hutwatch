"""robots.txt compliance check, run once at startup."""
from __future__ import annotations

from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser


class RobotsDisallowedError(Exception):
    pass


def check_allowed(url: str, user_agent: str) -> None:
    """Raise RobotsDisallowedError if robots.txt forbids fetching `url`."""
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
    except OSError:
        # robots.txt unreachable: fail safe by treating it as unreadable but
        # not fatal, since many sites simply have no robots.txt at all.
        return

    if not parser.can_fetch(user_agent, url):
        raise RobotsDisallowedError(
            f"robots.txt at {robots_url} disallows fetching {url} for User-Agent {user_agent!r}"
        )
