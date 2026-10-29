"""
Traffic router handling observation submissions.
"""

from fastapi import APIRouter
from app.schemas import ManualObservationRequest, ManualObservationResponse
from app.inputs.manual import normalize_manual_counts
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
