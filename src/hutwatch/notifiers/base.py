from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class Notification:
    subject: str
    body: str


class Notifier(Protocol):
    def send(self, notification: Notification) -> None: ...
