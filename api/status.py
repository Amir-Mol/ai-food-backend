"""
Recommendation generation status endpoint.
Frontend polls this every 3 seconds to know when recommendations are ready.

PHASE 4: Added logging for polling patterns and generation lifecycle tracking.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone, timedelta
from typing import Annotated, Optional

from api.auth import get_current_active_user
from prisma.models import User

logger = logging.getLogger(__name__)

router = APIRouter()


class RecommendationStatus:
    """Response model for recommendation status"""
    status: str  # "idle" | "summarizing" | "generating" | "ready"
    recommendationsReadyAt: Optional[datetime] = None
    nextAllowedGenerationAt: Optional[datetime] = None


@router.get("/recommendation-status", tags=["Status"])
async def get_recommendation_status(current_user: Annotated[User, Depends(get_current_active_user)]):
    """
    Returns current generation status and timing info for recommendations.
    
    PHASE 4 IMPROVEMENTS:
    - Logs polling patterns for observability
    - Tracks generation lifecycle
    - No sensitive data in logs
    
    Frontend polls this endpoint every 3 seconds.
    
    Response:
    {
        "status": "idle" | "summarizing" | "generating" | "ready",
        "recommendationsReadyAt": ISO datetime or null,
        "waitingMinutes": number of minutes to wait or null
    }
    
    Frontend logic:
    - If status == "ready": Auto-navigate to results screen
    - If status in ["summarizing", "generating"]: Show loading spinner
    - If waitingMinutes is set: Show countdown timer
    """
    user_id = current_user.id
    status = current_user.recommendationGenerationStatus or "idle"
    
    # Calculate waitingMinutes if user is rate-limited
    waiting_minutes = None
    if current_user.nextAllowedGenerationAt and current_user.nextAllowedGenerationAt > datetime.now(timezone.utc):
        remaining_seconds = (current_user.nextAllowedGenerationAt - datetime.now(timezone.utc)).total_seconds()
        waiting_minutes = int(remaining_seconds // 60)
    
    # PHASE 4: Log polling with context-aware messages
    if status == "ready":
        logger.info(f"[{user_id}] Status poll: recommendations ready (ready at {current_user.recommendationsReadyAt})")
    elif status in ["summarizing", "generating"]:
        logger.debug(f"[{user_id}] Status poll: {status} in progress")
    elif waiting_minutes:
        logger.debug(f"[{user_id}] Status poll: rate-limited ({waiting_minutes}m remaining)")
    else:
        logger.debug(f"[{user_id}] Status poll: idle")
    
    response = {
        "status": status,
        "recommendationsReadyAt": current_user.recommendationsReadyAt,
    }
    
    if waiting_minutes:
        response["waitingMinutes"] = waiting_minutes
    
    return response
