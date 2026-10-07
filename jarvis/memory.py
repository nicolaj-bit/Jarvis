"""Hukommelse: samtalen gemmes i SQLite.

Hver besked gemmes præcis som den blev sendt til/fra Claude (JSON), så
dagens samtale kan genindlæses uændret efter en genstart. Beskeder fra én
tur gemmes samlet i én transaktion, så databasen aldrig indeholder en halv
værktøjsrunde.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    day         TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    text        TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_messages_day ON messages(day, id);
"""


def _plain_text(content: object) -> str:
    """Den læsbare tekst i en besked, til søgning og overblik i databasen."""
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(parts)


class Memory:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.executescript(SCHEMA)
        self._lock = threading.Lock()

    def load_day(self, day: date | None = None) -> list[dict]:
        day = day or date.today()
        with self._lock:
            rows = self._conn.execute(
                "SELECT role, content FROM messages WHERE day = ? ORDER BY id",
                (day.isoformat(),),
            ).fetchall()
        return [{"role": role, "content": json.loads(content)} for role, content in rows]

    def save_turn(self, messages: list[dict], day: date | None = None) -> None:
        if not messages:
            return
        day = day or date.today()
        now = datetime.now().isoformat(timespec="seconds")
        rows = [
            (
                day.isoformat(),
                now,
                m["role"],
                json.dumps(m["content"], ensure_ascii=False),
                _plain_text(m["content"]),
            )
            for m in messages
        ]
        with self._lock, self._conn:
            self._conn.executemany(
                "INSERT INTO messages (day, created_at, role, content, text) VALUES (?, ?, ?, ?, ?)",
                rows,
            )

    def close(self) -> None:
        self._conn.close()
