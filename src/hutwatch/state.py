"""SQLite-backed state: every check logged, plus alert-transition tracking.

Transition rule (requirement 6): send an availability alert only when beds
crosses from below-threshold to at-or-above-threshold. Once alerted, stay
"armed-off" until availability drops back below threshold, at which point the
next crossing will alert again ("re-arming").
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class CheckRecord:
    timestamp: str
    label: str | None
    beds: int | None
    room_type: str | None
    http_status: int | None
    error: str | None


class StateStore:
    def __init__(self, db_path: str | Path) -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                label TEXT,
                beds INTEGER,
                room_type TEXT,
                http_status INTEGER,
                error TEXT
            );

            CREATE TABLE IF NOT EXISTS monitor_state (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )
        self._conn.commit()
        self._migrate_add_label_column()

    def _migrate_add_label_column(self) -> None:
        """Adds the 'label' column to pre-existing databases created before
        multi-target support was added."""
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(checks)")}
        if "label" not in columns:
            self._conn.execute("ALTER TABLE checks ADD COLUMN label TEXT")
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # -- checks log ---------------------------------------------------

    def log_check(
        self,
        beds: int | None,
        room_type: str | None,
        http_status: int | None,
        error: str | None,
        timestamp: datetime | None = None,
        label: str | None = None,
    ) -> None:
        ts = (timestamp or datetime.now(timezone.utc)).isoformat()
        self._conn.execute(
            "INSERT INTO checks (timestamp, label, beds, room_type, http_status, error) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ts, label, beds, room_type, http_status, error),
        )
        self._conn.commit()

    def recent_checks(self, limit: int = 20, label: str | None = None) -> list[CheckRecord]:
        if label is None:
            rows = self._conn.execute(
                "SELECT timestamp, label, beds, room_type, http_status, error "
                "FROM checks ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT timestamp, label, beds, room_type, http_status, error "
                "FROM checks WHERE label = ? ORDER BY id DESC LIMIT ?",
                (label, limit),
            ).fetchall()
        return [
            CheckRecord(
                timestamp=r["timestamp"],
                label=r["label"],
                beds=r["beds"],
                room_type=r["room_type"],
                http_status=r["http_status"],
                error=r["error"],
            )
            for r in rows
        ]

    # -- generic key/value state ---------------------------------------

    def get_value(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM monitor_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_value(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO monitor_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()

    # -- alert-transition state (armed / not armed) ---------------------

    _ARMED_KEY_PREFIX = "alert_armed"

    def is_armed(self, label: str = "default") -> bool:
        """Armed means: the next at-or-above-threshold result should alert."""
        value = self.get_value(f"{self._ARMED_KEY_PREFIX}:{label}")
        return value is None or value == "1"

    def set_armed(self, armed: bool, label: str = "default") -> None:
        self.set_value(f"{self._ARMED_KEY_PREFIX}:{label}", "1" if armed else "0")

    def should_alert(self, beds: int | None, threshold: int, label: str = "default") -> bool:
        """Apply the transition rule and update armed state accordingly.

        Returns True exactly when this check should trigger an availability
        alert (a fresh crossing from below-threshold to at-or-above).
        Each `label` (target) is tracked independently.
        """
        meets_threshold = beds is not None and beds >= threshold
        armed = self.is_armed(label)

        if meets_threshold:
            if armed:
                self.set_armed(False, label)
                return True
            return False
        else:
            # Below threshold (or unknown) re-arms for the next crossing.
            if not armed:
                self.set_armed(True, label)
            return False

    # -- consecutive-failure tracking -----------------------------------

    _FAILURE_KEY_PREFIX = "consecutive_failures"

    def get_consecutive_failures(self, label: str = "default") -> int:
        value = self.get_value(f"{self._FAILURE_KEY_PREFIX}:{label}")
        return int(value) if value is not None else 0

    def record_success(self, label: str = "default") -> None:
        self.set_value(f"{self._FAILURE_KEY_PREFIX}:{label}", "0")

    def record_failure(self, label: str = "default") -> int:
        count = self.get_consecutive_failures(label) + 1
        self.set_value(f"{self._FAILURE_KEY_PREFIX}:{label}", str(count))
        return count

    # -- heartbeat tracking ----------------------------------------------

    _LAST_HEARTBEAT_KEY = "last_heartbeat_date"

    def last_heartbeat_date(self) -> str | None:
        return self.get_value(self._LAST_HEARTBEAT_KEY)

    def set_last_heartbeat_date(self, iso_date: str) -> None:
        self.set_value(self._LAST_HEARTBEAT_KEY, iso_date)
