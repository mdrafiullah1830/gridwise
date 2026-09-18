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
            total_carbon_kg REAL DEFAULT 0,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_runs_scenario ON runs(scenario_id);
        CREATE INDEX IF NOT EXISTS idx_runs_created  ON runs(created_at DESC);
        """
    )
    # Migration: add total_carbon_kg column if missing
    try:
        conn.execute("SELECT total_carbon_kg FROM runs LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE runs ADD COLUMN total_carbon_kg REAL DEFAULT 0")
        conn.commit()


def save_run(
    scenario_id: str,
    notes: list[str],
    response: dict,
    baseline: dict | None = None,
    elapsed_ms: float | None = None,
    total_carbon_kg: float = 0.0,
) -> int:
    conn = _get_conn()
    cur = conn.execute(
        "INSERT INTO runs (scenario_id, notes, response, baseline, elapsed_ms, total_carbon_kg) VALUES (?, ?, ?, ?, ?, ?)",
        (scenario_id, json.dumps(notes), json.dumps(response), json.dumps(baseline) if baseline else None, elapsed_ms, total_carbon_kg),
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


def get_cost_trend(limit: int = 50, scenario_id: str | None = None) -> list[dict]:
    """Return cost trend data for historical runs."""
    conn = _get_conn()
    if scenario_id:
        rows = conn.execute(
            "SELECT id, scenario_id, response, total_carbon_kg, created_at FROM runs WHERE scenario_id = ? ORDER BY created_at DESC LIMIT ?",
            (scenario_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, scenario_id, response, total_carbon_kg, created_at FROM runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    trend = []
    for r in rows:
        resp = json.loads(r["response"]) if r["response"] else {}
        trend.append({
            "run_id": r["id"],
            "scenario_id": r["scenario_id"],
            "total_cost_bdt": resp.get("total_cost_bdt", 0),
            "total_grid_kwh": resp.get("total_grid_kwh", 0),
            "total_carbon_kg": r["total_carbon_kg"] or resp.get("total_carbon_kg", 0),
            "created_at": r["created_at"],
        })
    return list(reversed(trend))  # oldest first for charting


def get_carbon_stats() -> dict:
    """Return aggregate carbon statistics across all runs."""
    conn = _get_conn()
    row = conn.execute(
        """
        SELECT
            COUNT(*) as total_runs,
            COALESCE(SUM(total_carbon_kg), 0) as total_carbon_kg,
            COALESCE(AVG(total_carbon_kg), 0) as avg_carbon_kg,
            COALESCE(MAX(total_carbon_kg), 0) as best_carbon_saving_kg
        FROM runs WHERE total_carbon_kg > 0
        """
    ).fetchone()
    best = conn.execute(
        "SELECT id FROM runs WHERE total_carbon_kg > 0 ORDER BY total_carbon_kg DESC LIMIT 1"
    ).fetchone()
    return {
        "total_runs": row["total_runs"] if row else 0,
        "total_carbon_kg": round(row["total_carbon_kg"], 2) if row else 0,
        "avg_carbon_kg": round(row["avg_carbon_kg"], 2) if row else 0,
        "best_run_id": best["id"] if best else None,
        "best_carbon_saving_kg": round(row["best_carbon_saving_kg"], 2) if row else 0,
    }
