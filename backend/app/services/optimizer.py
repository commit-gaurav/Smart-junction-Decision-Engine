"""
Traffic Phase Optimizer Service.

Scores junction approaches based on demand (vehicle count) and waiting time,
enforces fairness maximum wait ceilings (90s), resolves ties deterministically,
and clamps recommended green durations to configured boundaries.
"""

from typing import Any, Dict, List, Optional
from app.config import Settings

APPROACH_ORDER = {"N": 0, "E": 1, "S": 2, "W": 3}


def score_approaches(
    approach_data: List[Dict[str, Any]],
    settings: Settings,
) -> List[Dict[str, Any]]:
    """
    Compute demand_score, wait_score, and total_score for each approach.
    Formula:
      - demand_score = vehicle_count * demand_weight
      - wait_score = waiting_seconds * wait_weight
      - total_score = demand_score + wait_score
    """
    scored = []
    for item in approach_data:
        v_count = int(item["vehicle_count"])
        w_sec = int(item["waiting_seconds"])
        d_score = float(v_count) * settings.demand_weight
        w_score = float(w_sec) * settings.wait_weight
        t_score = round(d_score + w_score, 4)

        scored.append(
            {
                "code": item["code"],
                "vehicle_count": v_count,
                "waiting_seconds": w_sec,
                "demand_score": d_score,
                "wait_score": w_score,
                "total_score": t_score,
                "selected": False,
            }
        )
    return scored


def clamp_green(
    raw_green_seconds: int,
    min_green_seconds: int,
    max_green_seconds: int,
) -> int:
    """
    Enforce min/max green duration boundaries.
    """
    return max(min_green_seconds, min(raw_green_seconds, max_green_seconds))


def recommend_phase(
    scored_approaches: List[Dict[str, Any]],
    current_phase_code: Optional[str],
    settings: Settings,
) -> Dict[str, Any]:
    """
    Evaluate scored approaches and select the next green phase.
    Rules:
      1. Fairness Ceiling: Any approach with waiting_seconds >= fairness_max_wait_seconds (90s)
         is eligible for fairness priority override.
      2. Demand/Wait Optimization: Approach with highest total_score is selected.
      3. Deterministic Tie Breaking: If scores tie, break by waiting_seconds, then
         vehicle_count, then canonical NESW order ('N' < 'E' < 'S' < 'W').
      4. Bounded Green: Allocates min_green + vehicle_count * extension_rate, clamped to [min, max].
    """
    if not scored_approaches:
        raise ValueError("Cannot recommend phase with empty approach scores")

    # 1. Fairness check: approaches reaching the fairness ceiling (>= 90s)
    fairness_candidates = [
        a for a in scored_approaches if a["waiting_seconds"] >= settings.fairness_max_wait_seconds
    ]

    selected: Dict[str, Any]
    reason: str

    if fairness_candidates:
        # Sort fairness candidates: highest wait time, then highest total score, then canonical order
        fairness_candidates.sort(
            key=lambda a: (-a["waiting_seconds"], -a["total_score"], APPROACH_ORDER.get(a["code"], 99))
        )
        selected = fairness_candidates[0]
        reason = (
            f"Fairness priority override: Approach {selected['code']} reached "
            f"{selected['waiting_seconds']}s wait time (ceiling: {settings.fairness_max_wait_seconds}s); "
            f"prioritized over general demand."
        )
    else:
        # 2. Score optimization and tie resolution
        max_score = max(a["total_score"] for a in scored_approaches)
        tied = [a for a in scored_approaches if abs(a["total_score"] - max_score) < 1e-5]

        if len(tied) > 1:
            # Deterministic tie-breaker: wait time > vehicle count > canonical NESW order
            tied.sort(
                key=lambda a: (-a["waiting_seconds"], -a["vehicle_count"], APPROACH_ORDER.get(a["code"], 99))
            )
            selected = tied[0]
            tied_codes = ", ".join(t["code"] for t in tied)
            reason = (
                f"Tied total score ({max_score:.2f}) among [{tied_codes}]; "
                f"resolved by deterministic tie-breaker (wait > demand > canonical order) to approach {selected['code']}."
            )
        else:
            selected = tied[0]
            reason = (
                f"Highest combined score ({selected['total_score']:.2f}) "
                f"[Demand: {selected['demand_score']:.1f}, Wait: {selected['wait_score']:.1f}]."
            )

    # Mark selection
    for a in scored_approaches:
        a["selected"] = a["code"] == selected["code"]

    # 3. Calculate and clamp green duration
    raw_green = settings.min_green_seconds + int(
        selected["vehicle_count"] * settings.green_extension_seconds_per_vehicle
    )
    recommended_green = clamp_green(
        raw_green, settings.min_green_seconds, settings.max_green_seconds
    )

    return {
        "next_phase_code": selected["code"],
        "recommended_green_seconds": recommended_green,
        "reason": reason,
        "scored_approaches": scored_approaches,
    }

