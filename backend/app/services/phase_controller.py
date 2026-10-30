"""
Centralized Phase Controller Service.

Enforces safe simulated signal state transitions:
  GREEN -> YELLOW -> ALL_RED -> next GREEN
Only one approach active at a time.
Boundary-only updates: Ordinary plan changes and operator-confirmed emergency priority
never interrupt active green; they queue in next_phase_code / planned decision until
the safe clearance boundary (after yellow and all-red clearance).
"""

from datetime import datetime, timezone, timedelta
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
    Fetch the authoritative singleton row from signal_state joined with decision details
    and pending/scheduled emergency status.
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

        # Check for active emergency requests
        em_cursor = conn.execute(
            """
            SELECT e.id, a.code, e.status, e.trust_status
            FROM emergency_requests e
            JOIN approaches a ON e.approach_id = a.id
            WHERE e.status IN ('scheduled', 'pending')
            ORDER BY e.id DESC LIMIT 1;
            """
        )
        em_row = em_cursor.fetchone()
        em_status = "none"
        if em_row:
            em_status = f"{em_row['status']} (Approach {em_row['code']})"

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
            "emergency_status": em_status,
            "recommendation": rec,
        }


def queue_plan(decision_id: int, next_phase_code: str) -> None:
    """
    Queue an ordinary plan change into the singleton signal_state row.
    Never interrupts an active green; updates next_phase_code and active_decision_id
    so advance_state applies it at the next safe boundary.
    Note: If a trusted emergency is already scheduled, ordinary plans do not overwrite it.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        # Check if an emergency request is actively scheduled
        em_cursor = conn.execute(
            "SELECT id FROM emergency_requests WHERE status = 'scheduled' LIMIT 1;"
        )
        if em_cursor.fetchone():
            # Retain scheduled emergency priority
            return

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


def schedule_emergency(
    approach_code: str,
    operator_confirmed: bool,
    expires_in_seconds: int = 60,
) -> Dict[str, Any]:
    """
    Validate, record, and schedule an operator-confirmed emergency priority request.
    Strictly requires operator_confirmed=True; rejects untrusted requests.
    Schedules the approach for service at the next safe boundary after yellow and all-red clearance.
    Does NOT reset other approaches' wait times.
    """
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    expires_at = (now + timedelta(seconds=expires_in_seconds)).isoformat() if expires_in_seconds else None

    if not operator_confirmed:
        # Record rejected attempt for audit tracking
        with get_db() as conn:
            cur = conn.execute("SELECT id FROM approaches WHERE code = ?;", (approach_code,))
            app_row = cur.fetchone()
            if not app_row:
                raise ValueError(f"Unknown approach: {approach_code}")
            
            app_id = app_row["id"]
            reason = "Rejected: Emergency request lacked explicit operator confirmation."
            cursor = conn.execute(
                """
                INSERT INTO emergency_requests (
                    approach_id, requested_at, expires_at, trust_status, status,
                    request_ref, decision_reason, created_at
                ) VALUES (?, ?, ?, 'untrusted', 'rejected', ?, ?, ?);
                """,
                (app_id, now_iso, expires_at, f"ref-untrusted-{now.timestamp()}", reason, now_iso),
            )
            req_id = cursor.lastrowid

        return {
            "request_id": req_id,
            "status": "rejected",
            "scheduled_phase": None,
            "reason": reason,
        }

    # Operator confirmed: Trust and schedule at next safe boundary
    reason = (
        f"Trusted operator-confirmed emergency request for Approach {approach_code}; "
        f"scheduled at next safe boundary following yellow and all-red clearance."
    )

    with get_db() as conn:
        cur = conn.execute("SELECT id FROM approaches WHERE code = ?;", (approach_code,))
        app_row = cur.fetchone()
        if not app_row:
            raise ValueError(f"Unknown approach: {approach_code}")
        app_id = app_row["id"]

        # 1. Insert trusted emergency request
        cursor = conn.execute(
            """
            INSERT INTO emergency_requests (
                approach_id, requested_at, expires_at, trust_status, status,
                request_ref, decision_reason, created_at
            ) VALUES (?, ?, ?, 'trusted', 'scheduled', ?, ?, ?);
            """,
            (app_id, now_iso, expires_at, f"ref-em-{now.timestamp()}", reason, now_iso),
        )
        req_id = cursor.lastrowid

        # 2. Record an overriding decision row for audit
        dec_cur = conn.execute(
            """
            INSERT INTO decisions (
                created_at, observation_id, emergency_request_id,
                current_phase_code, next_phase_code, recommended_green_seconds,
                reason, algorithm_version, execution_status, instruction_json
            ) VALUES (?, NULL, ?, NULL, ?, 25, ?, '1.0.0-emergency', 'planned', ?);
            """,
            (
                now_iso,
                req_id,
                approach_code,
                reason,
                '{"mode":"simulation_only","transmission_status":"not_sent","type":"emergency_override"}',
            ),
        )
        decision_id = dec_cur.lastrowid

        # 3. Schedule next phase in signal_state without interrupting active green
        conn.execute(
            """
            UPDATE signal_state
            SET next_phase_code = ?,
                active_decision_id = ?,
                updated_at = ?
            WHERE id = 1;
            """,
            (approach_code, decision_id, now_iso),
        )

    return {
        "request_id": req_id,
        "status": "scheduled",
        "scheduled_phase": approach_code,
        "reason": reason,
    }


def cancel_emergency(request_id: int) -> Dict[str, Any]:
    """
    Cancel a pending or scheduled emergency request.
    Reverts signal_state next_phase_code to default cyclic rotation if it was scheduled for this request.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cursor = conn.execute(
            """
            SELECT e.id, e.status, a.code
            FROM emergency_requests e
            JOIN approaches a ON e.approach_id = a.id
            WHERE e.id = ?;
            """,
            (request_id,),
        )
        req = cursor.fetchone()
        if not req:
            raise LookupError(f"Emergency request {request_id} not found")

        if req["status"] in ("cancelled", "served", "expired"):
            return {
                "request_id": request_id,
                "status": req["status"],
                "scheduled_phase": None,
                "reason": f"Request is already in '{req['status']}' state.",
            }

        # Update status to cancelled
        reason = f"Operator cancelled emergency request {request_id} for Approach {req['code']}."
        conn.execute(
            """
            UPDATE emergency_requests
            SET status = 'cancelled',
                decision_reason = ?
            WHERE id = ?;
            """,
            (reason, request_id),
        )

        # If this request was currently scheduled as next_phase, revert to cyclic order
        st_cur = conn.execute("SELECT phase_code, next_phase_code FROM signal_state WHERE id = 1;")
        st_row = st_cur.fetchone()
        if st_row and st_row["next_phase_code"] == req["code"]:
            curr_p = st_row["phase_code"] or "N"
            cycle_map = {"N": "E", "E": "S", "S": "W", "W": "N"}
            reverted_next = cycle_map.get(curr_p, "N")
            conn.execute(
                """
                UPDATE signal_state
                SET next_phase_code = ?,
                    active_decision_id = NULL,
                    updated_at = ?
                WHERE id = 1;
                """,
                (reverted_next, now_iso),
            )

        return {
            "request_id": request_id,
            "status": "cancelled",
            "scheduled_phase": None,
            "reason": reason,
        }


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
    If an emergency request was scheduled for this phase, marks it 'served'.
    Does NOT reset other approaches' wait clocks.
    """
    if elapsed_seconds <= 0:
        raise ValueError("elapsed_seconds must be a positive integer")

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

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
                    "SELECT recommended_green_seconds, emergency_request_id FROM decisions WHERE id = ?;",
                    (active_dec_id,),
                )
                dec_row = dec_cur.fetchone()
                if dec_row:
                    rec_green = dec_row["recommended_green_seconds"]
                    if dec_row["emergency_request_id"]:
                        # Mark emergency request as served
                        conn.execute(
                            "UPDATE emergency_requests SET status = 'served' WHERE id = ?;",
                            (dec_row["emergency_request_id"],),
                        )

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

        # Safety check
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
