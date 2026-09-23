"""Small local-only durable storage for completed transcript jobs."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from time import time
from typing import Any, Mapping


class LocalProtocolStore:
    """Persist JSON snapshots locally; audio never enters this database."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS completed_jobs (
                    job_id TEXT PRIMARY KEY,
                    result_json TEXT NOT NULL,
                    analysis_json TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )

    def save_result(self, job_id: str, result: Mapping[str, Any]) -> None:
        """Save a completed transcript and invalidate any derived protocol."""
        now = time()
        serialized = self._serialize(result)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO completed_jobs (job_id, result_json, analysis_json, created_at, updated_at)
                VALUES (?, ?, NULL, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    result_json = excluded.result_json,
                    analysis_json = NULL,
                    updated_at = excluded.updated_at
                """,
                (job_id, serialized, now, now),
            )

    def save_analysis(self, job_id: str, analysis: Mapping[str, Any]) -> None:
        with self._connect() as connection:
            updated = connection.execute(
                "UPDATE completed_jobs SET analysis_json = ?, updated_at = ? WHERE job_id = ?",
                (self._serialize(analysis), time(), job_id),
            )
        if updated.rowcount != 1:
            raise KeyError(job_id)

    def result_for(self, job_id: str) -> dict[str, Any] | None:
        return self._load_json(job_id, "result_json")

    def analysis_for(self, job_id: str) -> dict[str, Any] | None:
        return self._load_json(job_id, "analysis_json")

    def has(self, job_id: str) -> bool:
        with self._connect() as connection:
            return connection.execute("SELECT 1 FROM completed_jobs WHERE job_id = ?", (job_id,)).fetchone() is not None

    def delete(self, job_id: str) -> bool:
        with self._connect() as connection:
            deleted = connection.execute("DELETE FROM completed_jobs WHERE job_id = ?", (job_id,))
        if deleted.rowcount != 1:
            return False
        # Keep removed transcript text out of free SQLite pages.  This is a
        # best-effort local cleanup, not a claim about filesystem snapshots.
        with self._connect() as connection:
            connection.execute("VACUUM")
        return True

    def _load_json(self, job_id: str, column: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(f"SELECT {column} FROM completed_jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None or row[0] is None:
            return None
        value = json.loads(row[0])
        if not isinstance(value, dict):
            raise ValueError("Local protocol storage contains an invalid JSON object.")
        return value

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.execute("PRAGMA secure_delete = ON")
        return connection

    @staticmethod
    def _serialize(value: Mapping[str, Any]) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
