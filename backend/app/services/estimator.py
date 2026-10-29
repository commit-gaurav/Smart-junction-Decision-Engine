"""
Traffic estimator service.

Translates vehicle counts into standardized congestion levels ('low', 'medium', 'high')
and persists normalized multi-approach observations in SQLite.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from app.db import get_db
from app.schemas import ApproachObservationItem, ManualObservationResponse, CongestionLevel

# Congestion Threshold Rules (Editable Demo Constants):
# - LOW (0 to 4 vehicles): Fluid movement, short queue cleared within minimum green.
# - MEDIUM (5 to 12 vehicles): Moderate queue, requires standard green allocation.
# - HIGH (13+ vehicles): Heavy queue / saturated lane, requires maximum green allocation.
CONGESTION_THRESHOLD_LOW = 4
CONGESTION_THRESHOLD_MEDIUM = 12


def estimate_congestion(count: int) -> CongestionLevel:
    """
    Classify approach vehicle count into low, medium, or high congestion.
    """
    if count <= CONGESTION_THRESHOLD_LOW:
        return "low"
    elif count <= CONGESTION_THRESHOLD_MEDIUM:
        return "medium"
    return "high"


def build_observation(
    normalized_counts: Dict[str, Dict[str, int]],
    source: str = "manual",
    source_ref: Optional[str] = None,
) -> ManualObservationResponse:
    """
    Persist an observation and its 4 approach_observations rows in a single transaction.
    Returns the populated ManualObservationResponse.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    approach_items: List[ApproachObservationItem] = []

    with get_db() as conn:
        # 1. Resolve approach code to database IDs
        cursor = conn.execute("SELECT id, code FROM approaches;")
        approach_ids = {row["code"]: row["id"] for row in cursor.fetchall()}

        # 2. Insert parent observation
        cursor = conn.execute(
            """
            INSERT INTO observations (observed_at, source, source_ref, status, created_at)
            VALUES (?, ?, ?, 'accepted', ?);
            """,
            (now_iso, source, source_ref, now_iso),
        )
        observation_id = cursor.lastrowid

        # 3. Insert four approach_observations
        for code in ("N", "E", "S", "W"):
            data = normalized_counts.get(code, {"vehicle_count": 0, "waiting_seconds": 0})
            count = data["vehicle_count"]
            wait_sec = data["waiting_seconds"]
            congestion = estimate_congestion(count)
            approach_id = approach_ids[code]

            conn.execute(
                """
                INSERT INTO approach_observations (
                    observation_id, approach_id, vehicle_count, congestion, confidence, waiting_seconds, created_at
                ) VALUES (?, ?, ?, ?, 1.0, ?, ?);
                """,
                (observation_id, approach_id, count, congestion, wait_sec, now_iso),
            )

            approach_items.append(
                ApproachObservationItem(
                    code=code,
                    vehicle_count=count,
                    congestion=congestion,
                    waiting_seconds=wait_sec,
                )
            )

    return ManualObservationResponse(
        observation_id=observation_id,
        observed_at=now_iso,
        approaches=approach_items,
    )

