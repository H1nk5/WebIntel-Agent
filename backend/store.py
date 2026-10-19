"""SQLite persistence for analysis results and background job state."""

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class IntelStore:
    def __init__(self, database_path, history_limit=100):
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.history_limit = int(history_limit)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self):
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS analyses (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    page_type TEXT NOT NULL,
                    content_length INTEGER NOT NULL,
                    sentiment_label TEXT NOT NULL,
                    sentiment_score REAL NOT NULL,
                    result_json TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_analyses_fetched_at
                    ON analyses(fetched_at DESC);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_id TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(result_id) REFERENCES analyses(id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
                """
            )
            connection.execute(
                "UPDATE jobs SET status='failed', error='服务重启，任务已中断', updated_at=? "
                "WHERE status IN ('queued', 'running')",
                (utc_now(),),
            )

    def save_analysis(self, result):
        payload = result.model_dump(mode="json")
        analysis_id = uuid.uuid4().hex
        payload["analysis_id"] = analysis_id
        analysis = payload["analysis"]
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT INTO analyses
                   (id, url, title, page_type, content_length, sentiment_label,
                    sentiment_score, result_json, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    analysis_id,
                    payload["url"],
                    payload["title"],
                    payload["page_type"],
                    payload["content_length"],
                    analysis["sentiment_label"],
                    analysis["sentiment_score"],
                    json.dumps(payload, ensure_ascii=False),
                    payload["fetched_at"],
                ),
            )
            connection.execute(
                "DELETE FROM analyses WHERE id NOT IN "
                "(SELECT id FROM analyses ORDER BY fetched_at DESC LIMIT ?)",
                (self.history_limit,),
            )
        return analysis_id

    def list_history(self, limit=20):
        limit = max(1, min(int(limit), self.history_limit))
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """SELECT id, url, title, sentiment_label, sentiment_score, fetched_at
                   FROM analyses ORDER BY fetched_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            total = connection.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
        return [dict(row) for row in rows], total

    def get_analysis(self, analysis_id):
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT result_json FROM analyses WHERE id=?", (analysis_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def clear_history(self):
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM analyses")

    def create_job(self, url):
        job_id = uuid.uuid4().hex
        now = utc_now()
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO jobs(id, url, status, created_at, updated_at) VALUES (?, ?, 'queued', ?, ?)",
                (job_id, url, now, now),
            )
        return self.get_job(job_id)

    def update_job(self, job_id, status, *, result_id=None, error=None):
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE jobs SET status=?, result_id=?, error=?, updated_at=? WHERE id=?",
                (status, result_id, error, utc_now(), job_id),
            )
        return self.get_job(job_id)

    def get_job(self, job_id):
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return None
        job = dict(row)
        job["result"] = self.get_analysis(job["result_id"]) if job["result_id"] else None
        return job

    def list_jobs(self, limit=20):
        limit = max(1, min(int(limit), 100))
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]
