"""
Deterministic seeded traffic simulation adapter.

Generates reproducible traffic demand observations across approaches
using isolated pseudo-random number generator (PRNG) states.
Operates completely independently of computer vision or video models.
"""

import random
from typing import Dict, Optional
from app.services.estimator import build_observation
from app.schemas import SimulationObservationResponse, SimulationProfile

APPROACH_CODES = ("N", "E", "S", "W")


def generate_simulated_counts(seed: int, profile: SimulationProfile) -> Dict[str, Dict[str, int]]:
    """
    Generate deterministic vehicle counts and waiting times using an isolated PRNG instance.
    Profiles:
      - 'balanced': moderate, evenly distributed traffic across all approaches.
      - 'rush': asymmetric peak traffic (heavy North-South queue, lighter East-West queue).
      - 'sparse': low off-peak / night-time traffic across all approaches.
    """
    rng = random.Random(seed)
    counts: Dict[str, Dict[str, int]] = {}

    if profile == "rush":
        # Heavy arterial approaches (N, S) vs lighter cross streets (E, W)
        for code in APPROACH_CODES:
            if code in ("N", "S"):
                vehicle_count = rng.randint(14, 25)  # High congestion
                waiting_seconds = rng.randint(20, 55)
            else:
                vehicle_count = rng.randint(1, 5)   # Low congestion
                waiting_seconds = rng.randint(5, 20)
            counts[code] = {
                "vehicle_count": vehicle_count,
                "waiting_seconds": waiting_seconds,
            }
    elif profile == "sparse":
        # Low traffic across all approaches
        for code in APPROACH_CODES:
            counts[code] = {
                "vehicle_count": rng.randint(0, 3),   # Low congestion
                "waiting_seconds": rng.randint(0, 10),
            }
    else:
        # Default 'balanced': moderate traffic
        for code in APPROACH_CODES:
            counts[code] = {
                "vehicle_count": rng.randint(5, 10),  # Medium congestion
                "waiting_seconds": rng.randint(10, 30),
            }

    return counts


def generate_simulated_observation(
    seed: Optional[int] = None,
    profile: SimulationProfile = "balanced",
) -> SimulationObservationResponse:
    """
    Generate, estimate, and persist a simulated observation.
    Returns the observation response enriched with seed, profile, and decision: null.
    """
    effective_seed = 42 if seed is None else seed
    simulated_counts = generate_simulated_counts(effective_seed, profile)

    source_ref = f"profile={profile};seed={effective_seed}"
    obs_response = build_observation(
        simulated_counts,
        source="simulation",
        source_ref=source_ref,
    )

    return SimulationObservationResponse(
        observation_id=obs_response.observation_id,
        observed_at=obs_response.observed_at,
        approaches=obs_response.approaches,
        seed=effective_seed,
        profile=profile,
        decision=None,
    )

