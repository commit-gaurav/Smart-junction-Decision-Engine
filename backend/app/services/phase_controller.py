"""
Centralized Phase Controller Service.

Enforces safe simulated signal state transitions:
  GREEN -> YELLOW -> ALL_RED -> next GREEN
Only one approach active at a time.
Boundary-only updates: Ordinary plan changes never interrupt active green;
they queue in next_phase_code / planned decision until the transition boundary.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from app.config import get_settings
from app.db import get_db

VALID_STATES = ("GREEN", "YELLOW", "ALL_RED", "IDLE")
TRANSITION_MAP = {
    "IDLE": ("GREEN",),
    "GREEN": ("YELLOW",),
    "YELLOW": ("ALL_RED",),
    "ALL_RED": ("GREEN",),
}


def validate_transition(current_state: str, next_state: str) -> bool:
    """
    Validate whether transitioning from current_state to next_state is safe.
    Enforces the strict lifecycle: GREEN -> YELLOW -> ALL_RED -> GREEN (or IDLE -> GREEN).
    """
    allowed = TRANSITION_MAP.get(current_state, ())
    return next_state in allowed


def get_current_signal_state() -> Dict[str, Any]:
    """
    Fetch the authoritative singleton row from signal_state joined with decision details.
    """
    with get_db() as conn:
        cursor = conn.execute(
            """
            SELECT 
                s.id,
                s.phase_code,
                s.state,
                s.phase_started_at,
                s.state_started_at,
                s.remaining_seconds,
                s.next_phase_code,
                s.active_decision_id,
                s.updated_at,
                d.recommended_green_seconds,
                d.reason AS decision_reason,
                d.execution_status
            FROM signal_state s
            LEFT JOIN decisions d ON s.active_decision_id = d.id
            WHERE s.id = 1;
            """
        )
        row = cursor.fetchone()
        if not row:
            raise RuntimeError("Database missing singleton signal_state row (id=1)")

        rec = None
        if row["active_decision_id"]:
            rec = {
                "decision_id": row["active_decision_id"],
                "next_phase_code": row["next_phase_code"],
                "recommended_green_seconds": row["recommended_green_seconds"],
                "reason": row["decision_reason"],
                "execution_status": row["execution_status"],
            }

        return {
            "state": row["state"],
            "active_phase": row["phase_code"],
            "remaining_seconds": row["remaining_seconds"],
            "next_phase": row["next_phase_code"],
            "phase_started_at": row["phase_started_at"],
            "state_started_at": row["state_started_at"],
            "active_decision_id": row["active_decision_id"],
            "updated_at": row["updated_at"],
            "emergency_status": "none",
            "recommendation": rec,
        }


def queue_plan(decision_id: int, next_phase_code: str) -> None:
    """
    Queue an ordinary plan change into the singleton signal_state row.
    Never interrupts an active green; updates next_phase_code and active_decision_id
    so advance_state applies it at the next safe boundary.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """
            UPDATE signal_state
            SET next_phase_code = ?,
                active_decision_id = ?,
                updated_at = ?
            WHERE id = 1;
            """,
            (next_phase_code, decision_id, now_iso),
        )


def _get_phase_timings(phase_code: str) -> Tuple[int, int, int]:
    """
    Retrieve default min_green, yellow, and all_red durations for a phase from signal_phases.
    """
    settings = get_settings()
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT min_green_seconds, yellow_seconds, all_red_seconds FROM signal_phases WHERE phase_code = ?;",
            (phase_code,),
        )
        row = cursor.fetchone()
        if row:
            return (
                row["min_green_seconds"],
                row["yellow_seconds"],
                row["all_red_seconds"],
            )
    return (
        settings.min_green_seconds,
        settings.yellow_seconds,
        settings.all_red_seconds,
    )


def advance_state(elapsed_seconds: int = 1) -> Dict[str, Any]:
    """
    Advance the simulated junction signal state by elapsed_seconds.
    Ticks down the remaining duration. When the countdown completes (remaining_seconds <= 0):
      - IDLE -> GREEN (initializes with current/next phase)
      - GREEN -> YELLOW (active green completes)
      - YELLOW -> ALL_RED (yellow clearance completes)
      - ALL_RED -> GREEN (all clearance completes; switches to next_phase at the boundary)
    Updates execution_status of the applied decision to 'applied_simulated'.
    """
    if elapsed_seconds <= 0:
        raise ValueError("elapsed_seconds must be a positive integer")

    now_iso = datetime.now(timezone.utc).isoformat()

    with get_db() as conn:
        cursor = conn.execute("SELECT * FROM signal_state WHERE id = 1;")
        current = cursor.fetchone()
        if not current:
            raise RuntimeError("Singleton signal_state missing")

        curr_state = current["state"]
        curr_phase = current["phase_code"] or "N"
        next_phase = current["next_phase_code"] or "N"
        remaining = current["remaining_seconds"] - elapsed_seconds
        active_dec_id = current["active_decision_id"]
        phase_started = current["phase_started_at"]
        state_started = current["state_started_at"]

        # Default timings for active/next phases
        min_g, y_sec, r_sec = _get_phase_timings(curr_phase)

        # Still time remaining in the current state
        if remaining > 0 and curr_state != "IDLE":
            conn.execute(
                """
                UPDATE signal_state
                SET remaining_seconds = ?,
                    updated_at = ?
                WHERE id = 1;
                """,
                (remaining, now_iso),
            )
            return get_current_signal_state()

        # State expired (or IDLE): compute safe transition
        if curr_state == "IDLE":
            new_state = "GREEN"
            new_phase = curr_phase
            new_remaining = min_g
            phase_started = now_iso
            state_started = now_iso
        elif curr_state == "GREEN":
            new_state = "YELLOW"
            new_phase = curr_phase
            new_remaining = y_sec
            state_started = now_iso
        elif curr_state == "YELLOW":
            new_state = "ALL_RED"
            new_phase = curr_phase
            new_remaining = r_sec
            state_started = now_iso
        elif curr_state == "ALL_RED":
            # Safe boundary reached: switch to next_phase!
            new_state = "GREEN"
            new_phase = next_phase
            phase_started = now_iso
            state_started = now_iso

            # Resolve green duration: use active decision's recommended green if present, else min_green
            rec_green = min_g
            if active_dec_id:
                dec_cur = conn.execute(
                    "SELECT recommended_green_seconds FROM decisions WHERE id = ?;",
                    (active_dec_id,),
                )
                dec_row = dec_cur.fetchone()
                if dec_row:
                    rec_green = dec_row["recommended_green_seconds"]

                # Mark decision as applied in simulation
                conn.execute(
                    """
                    UPDATE decisions
                    SET execution_status = 'applied_simulated'
                    WHERE id = ?;
                    """,
                    (active_dec_id,),
                )
            new_remaining = rec_green

            # Next phase will default to cycle to next approach unless another decision is queued
            next_approaches = {"N": "E", "E": "S", "S": "W", "W": "N"}
            next_phase = next_approaches.get(new_phase, "N")
        else:
            raise ValueError(f"Unknown signal state: {curr_state}")

        # Validate safety check
        if not validate_transition(curr_state, new_state):
            raise ValueError(f"Invalid transition attempted: {curr_state} -> {new_state}")

        # Persist new state to singleton row
        conn.execute(
            """
            UPDATE signal_state
            SET phase_code = ?,
                state = ?,
                phase_started_at = ?,
                state_started_at = ?,
                remaining_seconds = ?,
                next_phase_code = ?,
                updated_at = ?
            WHERE id = 1;
            """,
            (
                new_phase,
                new_state,
                phase_started,
                state_started,
                new_remaining,
                next_phase,
                now_iso,
            ),
        )

    return get_current_signal_state()

