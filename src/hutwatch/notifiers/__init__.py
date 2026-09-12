from __future__ import annotations

from hutwatch.config import NotifiersConfig
from hutwatch.notifiers.base import Notifier


def build_notifiers(config: NotifiersConfig) -> list[Notifier]:
    notifiers: list[Notifier] = []
    for name in config.enabled:
        if name == "ntfy":
            from hutwatch.notifiers.ntfy import NtfyNotifier

            if config.ntfy is None:
                raise ValueError("notifiers.ntfy enabled but not configured")
            notifiers.append(NtfyNotifier(config.ntfy))
        elif name == "smtp":
            from hutwatch.notifiers.smtp import SmtpNotifier

            if config.smtp is None:
                raise ValueError("notifiers.smtp enabled but not configured")
            notifiers.append(SmtpNotifier(config.smtp))
        else:
            raise ValueError(f"Unknown notifier: {name!r}")
    return notifiers
