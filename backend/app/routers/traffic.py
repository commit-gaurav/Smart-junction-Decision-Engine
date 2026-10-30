"""
Traffic router handling observation submissions.
"""

from fastapi import APIRouter
from app.schemas import (
    ManualObservationRequest,
    ManualObservationResponse,
    SimulationObservationRequest,
    SimulationObservationResponse,
)
from app.inputs.manual import normalize_manual_counts
from app.inputs.simulation import generate_simulated_observation
from app.services.estimator import build_observation

router = APIRouter(prefix="/api", tags=["traffic"])


@router.post("/observations/manual", response_model=ManualObservationResponse)
def submit_manual_observation(payload: ManualObservationRequest):
    """
    Accept manual vehicle counts and optional wait times for all four approaches (N, E, S, W).
    Estimates congestion and persists the observation in SQLite.
    """
    normalized = normalize_manual_counts(payload)
    return build_observation(normalized, source="manual")


@router.post("/observations/simulate", response_model=SimulationObservationResponse)
def submit_simulated_observation(payload: SimulationObservationRequest = SimulationObservationRequest()):
    """
    Generate, estimate, and persist a simulated traffic observation using a deterministic seed and profile.
    Supports profiles: 'balanced', 'rush', and 'sparse'.
    """
    return generate_simulated_observation(seed=payload.seed, profile=payload.profile or "balanced")
