"""
Emergencies Router.

Handles operator-confirmed emergency priority requests and cancellations.
"""

from fastapi import APIRouter, HTTPException, status
from app.schemas import EmergencyCreateRequest, EmergencyResponse
from app.services.phase_controller import cancel_emergency, schedule_emergency

router = APIRouter(prefix="/api/emergencies", tags=["emergencies"])


@router.post("", response_model=EmergencyResponse)
def create_emergency_request(payload: EmergencyCreateRequest):
    """
    Submit an emergency priority request.
    Strictly requires operator_confirmed=True. Unconfirmed requests are rejected with 422.
    """
    if not payload.operator_confirmed:
        # Never infer trust without explicit operator confirmation
        result = schedule_emergency(
            approach_code=payload.approach,
            operator_confirmed=False,
            expires_in_seconds=payload.expires_in_seconds or 60,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=result["reason"],
        )

    try:
        return schedule_emergency(
            approach_code=payload.approach,
            operator_confirmed=True,
            expires_in_seconds=payload.expires_in_seconds or 60,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{request_id}/cancel", response_model=EmergencyResponse)
def cancel_emergency_request(request_id: int):
    """
    Cancel an existing pending or scheduled emergency request.
    Reverts signal_state next_phase_code if it was scheduled for this emergency.
    """
    try:
        return cancel_emergency(request_id=request_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

