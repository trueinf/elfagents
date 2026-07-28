"""Which runs exist, and what each one is about.

The graph's checkpointer already survives a restart — that is the whole point
of it being a file. What did not survive was knowing which threads exist: that
index lived in a module-level dict, so a redeploy left every paused run intact
on disk and unreachable, which is the same as losing it.

Kept in the same SQLite file as the checkpoints so persistence is one decision
rather than two, and mounting a volume covers both.
"""

from __future__ import annotations

from typing import Any

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS elfagent_runs (
    thread_id   TEXT PRIMARY KEY,
    subject_id  TEXT NOT NULL,
    use_case    TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS elfagent_runs_subject ON elfagent_runs (subject_id);
"""


class RunStore:
    def __init__(self, path: str) -> None:
        self.path = path

    async def setup(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(SCHEMA)
            await db.commit()

    async def record(self, thread_id: str, subject_id: str, use_case: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO elfagent_runs "
                "(thread_id, subject_id, use_case) VALUES (?, ?, ?)",
                (thread_id, subject_id, use_case),
            )
            await db.commit()

    async def subject_of(self, thread_id: str) -> str | None:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT subject_id FROM elfagent_runs WHERE thread_id = ?",
                (thread_id,),
            ) as cursor:
                row = await cursor.fetchone()
        return row[0] if row else None

    async def for_subject(self, subject_id: str) -> list[dict[str, Any]]:
        """Newest first — a resumed demo wants the run you just killed."""
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT thread_id, created_at FROM elfagent_runs "
                "WHERE subject_id = ? ORDER BY created_at DESC, rowid DESC",
                (subject_id,),
            ) as cursor:
                rows = await cursor.fetchall()
        return [{"thread_id": r[0], "created_at": r[1]} for r in rows]
