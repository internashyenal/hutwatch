from __future__ import annotations

import smtplib
from email.message import EmailMessage

from hutwatch.config import SmtpConfig
from hutwatch.notifiers.base import Notification


class SmtpNotifier:
    def __init__(self, config: SmtpConfig) -> None:
        self._config = config

    def send(self, notification: Notification) -> None:
        cfg = self._config
        msg = EmailMessage()
        msg["Subject"] = notification.subject
        msg["From"] = cfg.from_addr
        msg["To"] = cfg.to_addr
        msg.set_content(notification.body)

        with smtplib.SMTP(cfg.host, cfg.port, timeout=15) as server:
            if cfg.use_tls:
                server.starttls()
            if cfg.username:
                server.login(cfg.username, cfg.password)
            server.send_message(msg)
