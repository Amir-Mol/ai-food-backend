"""
Post-study survey endpoint.
Triggered after the user completes all 100 recommendations (isExperimentComplete=True).
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Annotated, Optional
from datetime import datetime, timezone

from api.auth import get_current_active_user
from prisma.models import User
from prisma import Json
from database import db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/survey",
    tags=["survey"],
)


class SurveySubmit(BaseModel):
    answers: dict          # { "q1": 4, "q2": 3, ..., "q14": "text", "q15": "" }
    timeSpentSeconds: Optional[int] = None


@router.post("/submit", status_code=status.HTTP_200_OK)
async def submit_survey(
    payload: SurveySubmit,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """
    Saves the post-study survey response and marks the user's survey as complete.

    - Idempotent: if the user already submitted, return 200 without duplicate insert.
    - Only allowed after experiment is complete (isExperimentComplete=True).
    """
    user_id = current_user.id

    # Guard: experiment must be complete before survey can be submitted
    if not current_user.isExperimentComplete:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Survey is only available after completing all recommendations.",
        )

    # Idempotency: if already submitted, just return success
    if current_user.surveyComplete:
        logger.info(f"[{user_id}] Survey already submitted — returning success")
        return {"status": "already_submitted"}

    try:
        await db.surveyresponse.create(
            data={
                "user": {"connect": {"id": user_id}},
                "answers": Json(payload.answers),
                "timeSpentSeconds": payload.timeSpentSeconds,
            }
        )
        await db.user.update(
            where={"id": user_id},
            data={"surveyComplete": True},
        )
        logger.info(f"[{user_id}] Survey submitted successfully (timeSpent={payload.timeSpentSeconds}s)")
        return {"status": "success"}

    except Exception as e:
        logger.error(f"[{user_id}] Failed to save survey: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save survey. Please try again.",
        )


@router.get("/status", status_code=status.HTTP_200_OK)
async def get_survey_status(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    """
    Returns whether the user needs to complete the survey.
    Used by AuthCheckScreen on app launch to resume mid-survey.
    """
    return {
        "surveyPending": current_user.isExperimentComplete and not current_user.surveyComplete,
        "surveyComplete": current_user.surveyComplete,
    }
