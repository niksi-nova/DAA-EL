# =============================================================================
# db.py — SQLite persistence for analysis results
# =============================================================================
# PURPOSE:
#   Replace the in-memory results_store dict in app.py with a durable store
#   so that results survive a server restart. A plain Python dict lives only
#   as long as the Flask process does; restarting the server (a crash, a
#   code change during development, a deploy) silently wipes every job_id a
#   client may still hold a reference to.
#
#   SQLite is the right tool here, not Postgres/Redis: this is a single-
#   process, single-file university project. SQLite needs no separate server,
#   ships with the Python standard library, and a single file on disk is
#   trivial to inspect, back up, or delete.
#
# SCHEMA:
#   One row per analysis job. The full result dict (counts + metrics) is
#   stored as a JSON blob in `result_json` — there is no need to normalise
#   it into separate columns since we only ever fetch a whole result by its
#   job_id, never query inside it.
# =============================================================================

import json
import os
import sqlite3
from contextlib import contextmanager
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results.db")


def init_db() -> None:
    """Create the results table if it does not already exist. Idempotent."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS results (
                job_id      TEXT PRIMARY KEY,
                filename    TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )


@contextmanager
def _connect():
    # check_same_thread=False: Flask's dev server may handle requests on
    # different threads than the one that called init_db(); each call here
    # still opens and closes its own short-lived connection, so there is no
    # shared mutable connection object being touched concurrently.
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_result(job_id: str, filename: str, result: dict) -> None:
    """Persist (or overwrite) one job's result dict, keyed by job_id."""
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO results (job_id, filename, result_json) "
            "VALUES (?, ?, ?)",
            (job_id, filename, json.dumps(result)),
        )


def get_result(job_id: str) -> Optional[dict]:
    """Fetch a previously stored result dict by job_id, or None if absent."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT result_json FROM results WHERE job_id = ?", (job_id,)
        ).fetchone()
    if row is None:
        return None
    return json.loads(row[0])


def list_results(limit: int = 50) -> list:
    """Return the most recent `limit` jobs as {job_id, filename, created_at}."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT job_id, filename, created_at FROM results "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {"job_id": r[0], "filename": r[1], "created_at": r[2]} for r in rows
    ]
