"""
Manual count input adapter.

Validates and normalizes user-submitted approach counts and waiting times.
Operates independently of video models or external runtimes.
"""

from typing import Dict
from app.schemas import ManualObservationRequest

APPROACH_CODES = ("N", "E", "S", "W")


def normalize_manual_counts(payload: ManualObservationRequest) -> Dict[str, Dict[str, int]]:
    """
    Transform validated manual count payload into a normalized dictionary
    keyed by approach code ('N', 'E', 'S', 'W').
    """
    counts_dict = payload.counts.model_dump()
    waits_dict = payload.waiting_seconds.model_dump() if payload.waiting_seconds else {}

    normalized: Dict[str, Dict[str, int]] = {}
    for code in APPROACH_CODES:
        normalized[code] = {
            "vehicle_count": counts_dict.get(code, 0),
            "waiting_seconds": waits_dict.get(code, 0),
        }

    return normalized

