"""
Recommendation generation status endpoint.
Frontend polls this every 3 seconds to know when recommendations are ready.

PHASE 4: Added logging for polling patterns and generation lifecycle tracking.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
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
        "nextAllowedGenerationAt": ISO datetime or null
    }
    
    Frontend logic:
    - If status == "ready": Auto-navigate to results screen
    - If status in ["summarizing", "generating"]: Show loading spinner
    - If nextAllowedGenerationAt in future: Show countdown timer
    """
    user_id = current_user.id
    status = current_user.recommendationGenerationStatus or "idle"
    
    # PHASE 4: Log polling with context-aware messages
    if status == "ready":
        logger.info(f"[{user_id}] Status poll: recommendations ready (ready at {current_user.recommendationsReadyAt})")
    elif status in ["summarizing", "generating"]:
        logger.debug(f"[{user_id}] Status poll: {status} in progress")
    elif current_user.nextAllowedGenerationAt and current_user.nextAllowedGenerationAt > datetime.utcnow():
        wait_time = (current_user.nextAllowedGenerationAt - datetime.utcnow()).total_seconds() / 60
        logger.debug(f"[{user_id}] Status poll: rate-limited ({wait_time:.1f}m remaining)")
    else:
        logger.debug(f"[{user_id}] Status poll: idle")
    
    return {
        "status": status,
        "recommendationsReadyAt": current_user.recommendationsReadyAt,
        "nextAllowedGenerationAt": current_user.nextAllowedGenerationAt
    }
