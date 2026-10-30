"""
Traffic router handling observation submissions and decision optimization.
"""

from typing import List
from fastapi import APIRouter
from app.config import get_settings
from app.schemas import (
    ApproachObservationItem,
    DecisionSummary,
    ManualObservationRequest,
    ManualObservationResponse,
    SimulationObservationRequest,
    SimulationObservationResponse,
)
from app.inputs.manual import normalize_manual_counts
from app.inputs.simulation import generate_simulated_observation
from app.services.estimator import build_observation
from app.services.history import get_current_phase, record_decision
from app.services.optimizer import recommend_phase, score_approaches
from app.services.phase_controller import queue_plan

router = APIRouter(prefix="/api", tags=["traffic"])


def process_and_record_decision(
    observation_id: int,
    approaches: List[ApproachObservationItem],
) -> DecisionSummary:
    """
    Score approaches, recommend next green phase, persist the decision
    and its four score rows atomically in SQLite, and queue the planned decision
    into the phase controller for boundary-only application.
    """
    settings = get_settings()
    current_phase = get_current_phase()

    approach_dicts = [
        {
            "code": a.code,
            "vehicle_count": a.vehicle_count,
            "waiting_seconds": a.waiting_seconds,
        }
        for a in approaches
    ]

    scored = score_approaches(approach_dicts, settings)
    recommendation = recommend_phase(scored, current_phase, settings)

    decision_id = record_decision(
        observation_id=observation_id,
        current_phase_code=current_phase,
        next_phase_code=recommendation["next_phase_code"],
        recommended_green_seconds=recommendation["recommended_green_seconds"],
        reason=recommendation["reason"],
        algorithm_version=settings.algorithm_version,
        scores=recommendation["scored_approaches"],
    )

    # Queue ordinary plan change without interrupting active phase
    queue_plan(decision_id, recommendation["next_phase_code"])

    return DecisionSummary(
        decision_id=decision_id,
        current_phase_code=current_phase,
        next_phase_code=recommendation["next_phase_code"],
        recommended_green_seconds=recommendation["recommended_green_seconds"],
        reason=recommendation["reason"],
        algorithm_version=settings.algorithm_version,
        execution_status="planned",
    )


@router.post("/observations/manual", response_model=ManualObservationResponse)
def submit_manual_observation(payload: ManualObservationRequest):
    """
    Accept manual vehicle counts and optional wait times for all four approaches (N, E, S, W).
    Estimates congestion, scores approaches, generates a planned decision, queues it, and persists in SQLite.
    """
    normalized = normalize_manual_counts(payload)
    response = build_observation(normalized, source="manual")
    response.decision = process_and_record_decision(response.observation_id, response.approaches)
    return response


@router.post("/observations/simulate", response_model=SimulationObservationResponse)
def submit_simulated_observation(payload: SimulationObservationRequest = SimulationObservationRequest()):
    """
    Generate, estimate, score, queue, and persist a simulated traffic observation and decision.
    Supports profiles: 'balanced', 'rush', and 'sparse'.
    """
    response = generate_simulated_observation(seed=payload.seed, profile=payload.profile or "balanced")
    response.decision = process_and_record_decision(response.observation_id, response.approaches)
    return response
