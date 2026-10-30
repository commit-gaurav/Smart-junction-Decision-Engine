"""
History and Decision Persistence Service.

Persists optimizer decisions, approach score breakdowns, and audit snapshots
in SQLite in atomic transactions.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.db import get_db


def get_current_phase() -> Optional[str]:
    """
    Query the current phase code from the singleton signal_state row.
    """
    with get_db() as conn:
        cursor = conn.execute("SELECT phase_code FROM signal_state WHERE id = 1;")
        row = cursor.fetchone()
        return row["phase_code"] if row else None


def record_decision(
    observation_id: int,
    current_phase_code: Optional[str],
    next_phase_code: str,
    recommended_green_seconds: int,
    reason: str,
    algorithm_version: str,
    scores: List[Dict[str, Any]],
) -> int:
    """
    Persist an optimizer decision and its four approach score rows in a single transaction.
    Includes a valid simulation-only instruction JSON placeholder.
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    # Valid simulation-only placeholder (not the final instruction contract)
    instruction_placeholder = {
        "schema_version": "1.0-placeholder",
        "mode": "simulation_only",
        "transmission_status": "not_sent",
        "notice": "Temporary placeholder for audit persistence; instruction builder implemented in a later slice",
        "junction_id": "demo-junction-1",
        "phase": {
            "code": next_phase_code,
            "green_seconds": recommended_green_seconds,
        },
        "created_at": now_iso,
    }
    instruction_json_str = json.dumps(instruction_placeholder)

    with get_db() as conn:
        # Resolve approach IDs from approach codes
        cursor = conn.execute("SELECT id, code FROM approaches;")
        approach_ids = {row["code"]: row["id"] for row in cursor.fetchall()}

        # 1. Insert decision row
        cursor = conn.execute(
            """
            INSERT INTO decisions (
                created_at, observation_id, emergency_request_id,
                current_phase_code, next_phase_code, recommended_green_seconds,
                reason, algorithm_version, execution_status, instruction_json
            ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, 'planned', ?);
            """,
            (
                now_iso,
                observation_id,
                current_phase_code,
                next_phase_code,
                recommended_green_seconds,
                reason,
                algorithm_version,
                instruction_json_str,
            ),
        )
        decision_id = cursor.lastrowid

        # 2. Insert decision_approach_scores rows for all four approaches
        score_rows = [
            (
                decision_id,
                approach_ids[s["code"]],
                float(s["demand_score"]),
                float(s["wait_score"]),
                float(s["total_score"]),
                1 if s.get("selected", False) else 0,
            )
            for s in scores
            if s["code"] in approach_ids
        ]
        conn.executemany(
            """
            INSERT INTO decision_approach_scores (
                decision_id, approach_id, demand_score, wait_score, total_score, selected
            ) VALUES (?, ?, ?, ?, ?, ?);
            """,
            score_rows,
        )

        return decision_id

