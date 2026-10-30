"""
Signals Router.

Exposes endpoints for querying the live simulated signal state
and advancing the simulation clock.
"""

from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.services.phase_controller import advance_state, get_current_signal_state

router = APIRouter(prefix="/api/signals", tags=["signals"])


class TickRequest(BaseModel):
    """Payload for advancing the simulated signal state clock."""
    elapsed_seconds: Optional[int] = Field(
        default=1,
        ge=1,
        description="Number of elapsed seconds to advance the signal state machine",
    )


class SignalStateResponse(BaseModel):
    """Response contract for GET /api/signals/current and POST /api/signals/tick."""
    state: str
    active_phase: Optional[str] = None
    remaining_seconds: int
    next_phase: Optional[str] = None
    updated_at: str
    emergency_status: str
    recommendation: Optional[Dict[str, Any]] = None


@router.get("/current", response_model=SignalStateResponse)
def read_current_signal():
    """
    Fetch the current simulated state, active phase, countdown, and active recommendations.
    """
    try:
        return get_current_signal_state()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tick", response_model=SignalStateResponse)
def tick_signal_state(payload: Optional[TickRequest] = None):
    """
    Advance the simulated state machine by elapsed_seconds (default 1).
    Enforces safe phase transitions (GREEN -> YELLOW -> ALL_RED -> next GREEN).
    """
    elapsed = payload.elapsed_seconds if payload and payload.elapsed_seconds else 1
    try:
        return advance_state(elapsed_seconds=elapsed)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

