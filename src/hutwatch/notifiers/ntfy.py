from __future__ import annotations

import httpx

from hutwatch.config import NtfyConfig
from hutwatch.notifiers.base import Notification


class NtfyNotifier:
    def __init__(self, config: NtfyConfig) -> None:
        self._url = f"{config.server.rstrip('/')}/{config.topic}"

    def send(self, notification: Notification) -> None:
        httpx.post(
            self._url,
            content=notification.body.encode("utf-8"),
            headers={"Title": notification.subject.encode("utf-8"), "Priority": "high"},
            timeout=10,
        )
