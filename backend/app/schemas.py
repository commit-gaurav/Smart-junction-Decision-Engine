"""
Pydantic schemas and request/response validation contracts.
"""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

ApproachCode = Literal["N", "E", "S", "W"]
CongestionLevel = Literal["low", "medium", "high"]
SimulationProfile = Literal["balanced", "rush", "sparse"]


class ApproachCounts(BaseModel):
    """Counts for all four mutually exclusive junction approaches."""
    N: int = Field(..., ge=0, description="Vehicle count for North approach")
    E: int = Field(..., ge=0, description="Vehicle count for East approach")
    S: int = Field(..., ge=0, description="Vehicle count for South approach")
    W: int = Field(..., ge=0, description="Vehicle count for West approach")


class ApproachWaitingSeconds(BaseModel):
    """Optional waiting times in seconds for approaches."""
    N: int = Field(default=0, ge=0, description="Waiting seconds on North approach")
    E: int = Field(default=0, ge=0, description="Waiting seconds on East approach")
    S: int = Field(default=0, ge=0, description="Waiting seconds on South approach")
    W: int = Field(default=0, ge=0, description="Waiting seconds on West approach")


class ManualObservationRequest(BaseModel):
    """
    Request payload for manual traffic count entry.
    Requires counts for N, E, S, W (all >= 0); waiting_seconds is optional.
    """
    counts: ApproachCounts
    waiting_seconds: Optional[ApproachWaitingSeconds] = None


class ApproachObservationItem(BaseModel):
    """Per-approach processed observation data."""
    code: ApproachCode
    vehicle_count: int = Field(..., ge=0)
    congestion: CongestionLevel
    waiting_seconds: int = Field(..., ge=0)


class DecisionSummary(BaseModel):
    """Summary of an optimizer decision persisted for an observation."""
    decision_id: int
    current_phase_code: Optional[str] = None
    next_phase_code: str
    recommended_green_seconds: int
    reason: str
    algorithm_version: str
    execution_status: str


class ManualObservationResponse(BaseModel):
    """Response contract for POST /api/observations/manual."""
    observation_id: int
    observed_at: str
    approaches: List[ApproachObservationItem]
    decision: Optional[DecisionSummary] = None


class SimulationObservationRequest(BaseModel):
    """
    Request payload for seeded traffic simulation.
    seed and profile are optional; defaults to seed=42 and profile='balanced'.
    """
    seed: Optional[int] = Field(default=None, description="Optional seed for deterministic reproducibility")
    profile: Optional[SimulationProfile] = Field(default="balanced", description="Simulation traffic profile")


class SimulationObservationResponse(ManualObservationResponse):
    """
    Response contract for POST /api/observations/simulate.
    Enriches the observation shape with simulation metadata and decision summary.
    """
    seed: int
    profile: SimulationProfile
