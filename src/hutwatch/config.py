"""Configuration loading: config.toml (non-secret) + .env (secrets)."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class HutConfig:
    provider: str
    url: str


@dataclass
class TargetConfig:
    label: str
    check_in: date
    nights: int
    beds_required: int


@dataclass
class FetchConfig:
    engine: str
    timeout_seconds: float
    contact_email: str


@dataclass
class PollingConfig:
    interval_minutes: float
    jitter_minutes: float
    min_interval_minutes: float
    backoff_initial_seconds: float
    backoff_max_seconds: float
    backoff_multiplier: float


@dataclass
class AlertsConfig:
    max_consecutive_failures: int
    heartbeat_hour_utc: int


@dataclass
class StateConfig:
    db_path: str


@dataclass
class NtfyConfig:
    topic: str
    server: str


@dataclass
class SmtpConfig:
    host: str
    port: int
    username: str
    password: str
    from_addr: str
    to_addr: str
    use_tls: bool


@dataclass
class NotifiersConfig:
    enabled: list[str]
    ntfy: NtfyConfig | None = None
    smtp: SmtpConfig | None = None


@dataclass
class Config:
    hut: HutConfig
    targets: list[TargetConfig]
    fetch: FetchConfig
    polling: PollingConfig
    alerts: AlertsConfig
    state: StateConfig
    notifiers: NotifiersConfig


def _env(name: str, default: str | None = None) -> str:
    val = os.environ.get(name, default)
    if val is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


def load_config(config_path: str | Path = "config.toml", env_path: str | Path | None = None) -> Config:
    """Load config.toml plus .env secrets into a validated Config object."""
    if env_path is not None:
        load_dotenv(env_path)
    else:
        load_dotenv()  # loads .env from CWD if present; no-op otherwise

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    hut = HutConfig(
        provider=raw["hut"]["provider"],
        url=raw["hut"]["url"],
    )
    targets = [
        TargetConfig(
            label=t["label"],
            check_in=date.fromisoformat(t["check_in"]),
            nights=int(t["nights"]),
            beds_required=int(t["beds_required"]),
        )
        for t in raw["targets"]
    ]
    fetch = FetchConfig(
        engine=raw["fetch"]["engine"],
        timeout_seconds=float(raw["fetch"]["timeout_seconds"]),
        contact_email=raw["fetch"]["contact_email"],
    )
    polling = PollingConfig(
        interval_minutes=float(raw["polling"]["interval_minutes"]),
        jitter_minutes=float(raw["polling"]["jitter_minutes"]),
        min_interval_minutes=float(raw["polling"]["min_interval_minutes"]),
        backoff_initial_seconds=float(raw["polling"]["backoff_initial_seconds"]),
        backoff_max_seconds=float(raw["polling"]["backoff_max_seconds"]),
        backoff_multiplier=float(raw["polling"]["backoff_multiplier"]),
    )
    alerts = AlertsConfig(
        max_consecutive_failures=int(raw["alerts"]["max_consecutive_failures"]),
        heartbeat_hour_utc=int(raw["alerts"]["heartbeat_hour_utc"]),
    )
    state = StateConfig(db_path=raw["state"]["db_path"])

    enabled = list(raw["notifiers"]["enabled"])
    ntfy_cfg = None
    if "ntfy" in enabled and "ntfy" in raw["notifiers"]:
        n = raw["notifiers"]["ntfy"]
        ntfy_cfg = NtfyConfig(topic=_env(n["topic_env"]), server=n["server"])
    smtp_cfg = None
    if "smtp" in enabled and "smtp" in raw["notifiers"]:
        s = raw["notifiers"]["smtp"]
        smtp_cfg = SmtpConfig(
            host=_env(s["host_env"], ""),
            port=int(_env(s["port_env"], "587")),
            username=os.environ.get(s["username_env"], ""),
            password=os.environ.get(s["password_env"], ""),
            from_addr=_env(s["from_env"], ""),
            to_addr=_env(s["to_env"], ""),
            use_tls=bool(s["use_tls"]),
        )

    notifiers = NotifiersConfig(enabled=enabled, ntfy=ntfy_cfg, smtp=smtp_cfg)

    return Config(
        hut=hut,
        targets=targets,
        fetch=fetch,
        polling=polling,
        alerts=alerts,
        state=state,
        notifiers=notifiers,
    )
