"""
Recommendation generation status endpoint.
Frontend polls this every 3 seconds to know when recommendations are ready.
"""

from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from typing import Annotated, Optional

from api.auth import get_current_active_user
from prisma.models import User

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
    
    Frontend uses this endpoint to poll for status every 3 seconds.
    
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
    return {
        "status": current_user.recommendationGenerationStatus or "idle",
        "recommendationsReadyAt": current_user.recommendationsReadyAt,
        "nextAllowedGenerationAt": current_user.nextAllowedGenerationAt
    }
