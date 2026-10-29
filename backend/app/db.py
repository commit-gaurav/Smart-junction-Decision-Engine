"""
Database module for SQLite schema initialization, connections, and seeding.

Enforces foreign keys, parameterized queries, and idempotent seed generation
for the four-way junction simulation.
"""

import sqlite3
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Generator
from contextlib import contextmanager

from app.config import get_settings


def get_db_path() -> Path:
    """
    Resolve the absolute path to the SQLite database file under backend/data/.
    Creates the directory if it does not yet exist.
    """
    settings = get_settings()
    # Handle sqlite:/// URI prefix if present
    raw_path = settings.database_url
    if raw_path.startswith("sqlite:///"):
        raw_path = raw_path[len("sqlite:///"):]

    p = Path(raw_path)
    if not p.is_absolute():
        # Anchor relative paths to the backend directory (parent of app/)
        backend_dir = Path(__file__).resolve().parent.parent
        # If raw_path starts with ./backend/ or backend/, strip it when anchoring to backend_dir
        parts = p.parts
        if len(parts) > 0 and parts[0] in ("backend", "."):
            if parts[0] == ".":
                parts = parts[1:]
            if len(parts) > 0 and parts[0] == "backend":
                parts = parts[1:]
        p = backend_dir.joinpath(*parts)

    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def get_connection() -> sqlite3.Connection:
    """
    Open an SQLite connection with foreign keys enabled on every connection
    and sqlite3.Row for dictionary-like row access.
    """
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager yielding a transactional SQLite connection with foreign keys ON.
    Automatically commits on success or rolls back on exception.
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA_SQL = """
-- Table: approaches
CREATE TABLE IF NOT EXISTS approaches (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE CHECK(code IN ('N', 'E', 'S', 'W')),
    display_name TEXT NOT NULL
);

-- Table: observations
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY,
    observed_at TEXT NOT NULL,
    source TEXT NOT NULL CHECK(source IN ('manual', 'simulation', 'video')),
    source_ref TEXT NULL,
    status TEXT NOT NULL CHECK(status IN ('accepted', 'partial', 'rejected')),
    created_at TEXT NOT NULL
);

-- Table: approach_observations
CREATE TABLE IF NOT EXISTS approach_observations (
    id INTEGER PRIMARY KEY,
    observation_id INTEGER NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
    approach_id INTEGER NOT NULL REFERENCES approaches(id),
    vehicle_count INTEGER NOT NULL CHECK(vehicle_count >= 0),
    congestion TEXT NOT NULL CHECK(congestion IN ('low', 'medium', 'high')),
    confidence REAL NULL CHECK(confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    waiting_seconds INTEGER NOT NULL DEFAULT 0 CHECK(waiting_seconds >= 0),
    created_at TEXT NOT NULL,
    UNIQUE(observation_id, approach_id)
);

-- Table: signal_phases
CREATE TABLE IF NOT EXISTS signal_phases (
    id INTEGER PRIMARY KEY,
    phase_code TEXT NOT NULL UNIQUE,
    approach_id INTEGER NOT NULL UNIQUE REFERENCES approaches(id),
    min_green_seconds INTEGER NOT NULL CHECK(min_green_seconds > 0),
    max_green_seconds INTEGER NOT NULL CHECK(max_green_seconds >= min_green_seconds),
    yellow_seconds INTEGER NOT NULL CHECK(yellow_seconds >= 0),
    all_red_seconds INTEGER NOT NULL CHECK(all_red_seconds >= 0),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1))
);

-- Table: emergency_requests
CREATE TABLE IF NOT EXISTS emergency_requests (
    id INTEGER PRIMARY KEY,
    approach_id INTEGER NOT NULL REFERENCES approaches(id),
    requested_at TEXT NOT NULL,
    expires_at TEXT NULL,
    trust_status TEXT NOT NULL CHECK(trust_status IN ('trusted', 'untrusted', 'rejected')),
    status TEXT NOT NULL CHECK(status IN ('pending', 'scheduled', 'served', 'expired', 'rejected', 'cancelled')),
    request_ref TEXT NULL UNIQUE,
    decision_reason TEXT NULL,
    created_at TEXT NOT NULL
);

-- Table: decisions
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    observation_id INTEGER NULL REFERENCES observations(id),
    emergency_request_id INTEGER NULL REFERENCES emergency_requests(id),
    current_phase_code TEXT NULL REFERENCES signal_phases(phase_code),
    next_phase_code TEXT NOT NULL REFERENCES signal_phases(phase_code),
    recommended_green_seconds INTEGER NOT NULL CHECK(recommended_green_seconds > 0),
    reason TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    execution_status TEXT NOT NULL CHECK(execution_status IN ('planned', 'applied_simulated', 'rejected', 'failed')),
    instruction_json TEXT NOT NULL
);

-- Table: decision_approach_scores
CREATE TABLE IF NOT EXISTS decision_approach_scores (
    id INTEGER PRIMARY KEY,
    decision_id INTEGER NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
    approach_id INTEGER NOT NULL REFERENCES approaches(id),
    demand_score REAL NOT NULL,
    wait_score REAL NOT NULL,
    total_score REAL NOT NULL,
    selected INTEGER NOT NULL DEFAULT 0 CHECK(selected IN (0, 1)),
    UNIQUE(decision_id, approach_id)
);

-- Table: signal_state (singleton row id=1)
CREATE TABLE IF NOT EXISTS signal_state (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    phase_code TEXT NULL REFERENCES signal_phases(phase_code),
    state TEXT NOT NULL CHECK(state IN ('GREEN', 'YELLOW', 'ALL_RED', 'IDLE')),
    phase_started_at TEXT NULL,
    state_started_at TEXT NOT NULL,
    remaining_seconds INTEGER NOT NULL CHECK(remaining_seconds >= 0),
    next_phase_code TEXT NULL REFERENCES signal_phases(phase_code),
    active_decision_id INTEGER NULL REFERENCES decisions(id),
    updated_at TEXT NOT NULL
);

-- Table: approach_waits
CREATE TABLE IF NOT EXISTS approach_waits (
    approach_id INTEGER PRIMARY KEY REFERENCES approaches(id),
    waiting_seconds INTEGER NOT NULL DEFAULT 0 CHECK(waiting_seconds >= 0),
    last_served_at TEXT NULL,
    updated_at TEXT NOT NULL
);

-- Indexes from PLAN.md Section 6
CREATE INDEX IF NOT EXISTS idx_observations_observed_at ON observations(observed_at);
CREATE INDEX IF NOT EXISTS idx_decisions_created_at ON decisions(created_at);
CREATE INDEX IF NOT EXISTS idx_emergency_requests_status_requested ON emergency_requests(status, requested_at);
"""


def init_db() -> None:
    """
    Initialize SQLite schema and seed initial configuration idempotently.
    Safe to execute repeatedly without duplicating seed rows.
    """
    settings = get_settings()
    now_iso = datetime.now(timezone.utc).isoformat()

    with get_db() as conn:
        # 1. Execute schema creation DDL
        conn.executescript(SCHEMA_SQL)

        # 2. Seed 4 approaches: N, E, S, W
        approaches_seed = [
            ("N", "North"),
            ("E", "East"),
            ("S", "South"),
            ("W", "West"),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO approaches (code, display_name) VALUES (?, ?);",
            approaches_seed,
        )

        # Map approach codes to their persisted database IDs
        cursor = conn.execute("SELECT id, code FROM approaches;")
        approach_id_by_code = {row["code"]: row["id"] for row in cursor.fetchall()}

        # 3. Seed signal_phases for each approach using approved demo defaults
        phases_seed = [
            (
                code,
                approach_id_by_code[code],
                settings.min_green_seconds,
                settings.max_green_seconds,
                settings.yellow_seconds,
                settings.all_red_seconds,
                1,
            )
            for code in ("N", "E", "S", "W")
            if code in approach_id_by_code
        ]
        conn.executemany(
            """
            INSERT OR IGNORE INTO signal_phases (
                phase_code, approach_id, min_green_seconds, max_green_seconds, yellow_seconds, all_red_seconds, enabled
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            phases_seed,
        )

        # 4. Seed approach_waits rows (one per approach)
        waits_seed = [
            (approach_id_by_code[code], 0, None, now_iso)
            for code in ("N", "E", "S", "W")
            if code in approach_id_by_code
        ]
        conn.executemany(
            """
            INSERT OR IGNORE INTO approach_waits (
                approach_id, waiting_seconds, last_served_at, updated_at
            ) VALUES (?, ?, ?, ?);
            """,
            waits_seed,
        )

        # 5. Seed singleton signal_state row (id = 1)
        conn.execute(
            """
            INSERT OR IGNORE INTO signal_state (
                id, phase_code, state, phase_started_at, state_started_at, remaining_seconds, next_phase_code, active_decision_id, updated_at
            ) VALUES (1, 'N', 'IDLE', NULL, ?, 0, 'N', NULL, ?);
            """,
            (now_iso, now_iso),
        )


def check_db_health() -> str:
    """
    Check database connectivity and verify seed data presence.
    Returns 'connected' if healthy, or an error description string.
    """
    try:
        with get_db() as conn:
            cursor = conn.execute("SELECT COUNT(*) AS cnt FROM approaches;")
            row = cursor.fetchone()
            if row and row["cnt"] == 4:
                return "connected"
            return "uninitialized"
    except Exception as e:
        return f"error: {str(e)}"


if __name__ == "__main__":
    init_db()
    health = check_db_health()
    print(f"Database initialized. Health check: {health}")
    p = get_db_path()
    print(f"Database path: {p}")

