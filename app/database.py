"""SQLite-backed run history for GridWise."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "gridwise.db"
_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _local.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _init_schema(_local.conn)
    return _local.conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_id TEXT    NOT NULL,
            notes       TEXT    NOT NULL,
            response    TEXT    NOT NULL,
            baseline    TEXT,
            elapsed_ms  REAL,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_runs_scenario ON runs(scenario_id);
        CREATE INDEX IF NOT EXISTS idx_runs_created  ON runs(created_at DESC);
        """
    )


def save_run(
    scenario_id: str,
    notes: list[str],
    response: dict,
    baseline: dict | None = None,
    elapsed_ms: float | None = None,
) -> int:
    conn = _get_conn()
    cur = conn.execute(
        "INSERT INTO runs (scenario_id, notes, response, baseline, elapsed_ms) VALUES (?, ?, ?, ?, ?)",
        (scenario_id, json.dumps(notes), json.dumps(response), json.dumps(baseline) if baseline else None, elapsed_ms),
    )
    conn.commit()
    run_id = cur.lastrowid
    logger.info("Saved run #%d for scenario %s", run_id, scenario_id)
    return run_id


def get_runs(limit: int = 50, offset: int = 0) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, scenario_id, notes, elapsed_ms, created_at FROM runs ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    return [dict(r) for r in rows]


def get_run(run_id: int) -> dict | None:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["response"] = json.loads(d["response"]) if d["response"] else None
    d["baseline"] = json.loads(d["baseline"]) if d["baseline"] else None
    d["notes"] = json.loads(d["notes"]) if d["notes"] else []
    return d


def delete_run(run_id: int) -> bool:
    conn = _get_conn()
    cur = conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
    conn.commit()
    return cur.rowcount > 0


def get_stats() -> dict:
    conn = _get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as total_runs, MIN(created_at) as first_run, MAX(created_at) as last_run FROM runs"
    ).fetchone()
    return dict(row) if row else {"total_runs": 0, "first_run": None, "last_run": None}
