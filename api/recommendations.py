from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, Annotated, List, Dict
import asyncio
import logging
import json
from datetime import datetime

from api.auth import get_current_active_user
from prisma.models import User
from database import db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/recommendations",
    tags=["recommendations"],
)


class MealRecommendation(BaseModel):
    id: str
    name: str
    imageUrl: str
    fsaHealthScore: int = Field(..., ge=4, le=12)

class NutritionalInfo(BaseModel):
    """Detailed nutritional information for a meal."""
    calories: str
    protein: str
    carbs: str
    fat: str

class MealRecommendationDetail(MealRecommendation):
    """Extends MealRecommendation with full details for the meal screen."""
    description: str
    nutritionalInfo: NutritionalInfo
    ingredients: List[str]
    recipeUrl: str
    aiExplanation: str


class RecommendationsResponse(BaseModel):
    status: str
    showTransparencyFeatures: bool
    recommendations: List[MealRecommendation]

class FeedbackCreate(BaseModel):
    """Model for creating feedback on a meal recommendation."""
    liked: bool
    healthinessScore: int = Field(..., ge=1, le=5)
    tastinessScore: int = Field(..., ge=1, le=5)
    intentToTryScore: int = Field(..., ge=1, le=5)

@router.get("/", response_model=RecommendationsResponse)
async def get_recommendations(
    current_user: Annotated[User, Depends(get_current_active_user)],
    mealType: Optional[str] = None,
) -> RecommendationsResponse:
    """
    Returns pre-generated recommendations for the user.
    
    PHASE A STEP 3: Returns real recommendations stored in user.recommendations (JSON field)
    instead of mock data.
    
    Flow:
    1. Check if user.recommendations exists and is not empty
    2. IF yes: Parse JSON and return recommendations
    3. IF no: Return status info (not ready or error)
    
    Note: mealType parameter is deprecated (not used for Prisma-based recommendations)
    """
    user_id = current_user.id
    
    # Check if recommendations are available
    if not current_user.recommendations:
        logger.warning(f"[{user_id}] No pre-generated recommendations found")
        
        # Return error with status info for debugging
        return RecommendationsResponse(
            status="no-recommendations",
            showTransparencyFeatures=True,
            recommendations=[]
        )
    
    try:
        # Parse recommendations from JSON
        if isinstance(current_user.recommendations, str):
            recommendations_list = json.loads(current_user.recommendations)
        else:
            recommendations_list = current_user.recommendations
        
        logger.debug(f"[{user_id}] Retrieved {len(recommendations_list)} pre-generated recommendations")
        
        # Convert to MealRecommendation format
        # Assuming recommendations are already in the right format from generation
        meal_recommendations = []
        for rec in recommendations_list:
            try:
                meal_rec = MealRecommendation(
                    id=str(rec.get("recipeId", "")),
                    name=rec.get("name", "Unknown Recipe"),
                    imageUrl=rec.get("imageUrl", "https://via.placeholder.com/300"),
                    fsaHealthScore=int(rec.get("healthScore", 6))  # Default to 6 if missing
                )
                meal_recommendations.append(meal_rec)
            except Exception as e:
                logger.warning(f"[{user_id}] Failed to parse recommendation: {str(e)}")
                continue
        
        logger.info(f"[{user_id}] Returning {len(meal_recommendations)} recommendations")
        
        return RecommendationsResponse(
            status="success",
            showTransparencyFeatures=True,
            recommendations=meal_recommendations
        )
        
    except Exception as e:
        logger.error(f"[{user_id}] Failed to parse recommendations: {str(e)}")
        return RecommendationsResponse(
            status="error",
            showTransparencyFeatures=True,
            recommendations=[]
        )

@router.get("/{id}", response_model=MealRecommendationDetail)
async def get_recommendation_detail(id: str):
    """
    Returns detailed information for a specific meal recommendation.
    """
    meal = next((m for m in MOCK_MEALS_DB if m["id"] == id), None)

    if not meal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Meal not found"
        )

    detailed_meal_data = meal.copy()
    detailed_meal_data.update({
        "description": "A delicious and healthy meal option, perfect for any time of the day. Packed with nutrients to keep you energized.",
        "nutritionalInfo": {
            "calories": "450 kcal",
            "protein": "30g",
            "carbs": "20g",
            "fat": "25g"
        },
        "ingredients": ["Main Ingredient 1", "Vegetable/Fruit 1", "Healthy Fat Source", "Seasoning/Spice 1", "Dressing/Sauce"],
        "recipeUrl": "https://example.com/recipe/" + meal["id"],
        "aiExplanation": "This meal was recommended because it aligns with your preference for high-protein, low-carb meals and does not contain any of your disliked ingredients. Its high health score indicates a balanced nutritional profile."
    })

    return detailed_meal_data


@router.post("/{recommendation_id}/feedback")
async def submit_feedback(
    recommendation_id: str,
    feedback: FeedbackCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Dict[str, str]:
    """
    Submits feedback for a recommendation and triggers summarization if needed.
    
    PHASE 4 IMPROVEMENTS:
    - Better logging for feedback submission
    - Robust feedback counting with error handling
    - Safe async summarization triggering
    
    Flow:
    1. Find most recent training record for user + recommendation
    2. Update with feedback scores
    3. Count feedbacks since last summarization
    4. Trigger async summarization if count >= 5
    """
    user_id = current_user.id
    logger.info(
        f"[{user_id}] Feedback submission: recommendation={recommendation_id} "
        f"liked={feedback.liked} health={feedback.healthinessScore}"
    )
    
    # Find the most recent training record for this user and recommendation
    try:
        training_record = await db.trainingrecord.find_first(
            where={
                "userId": current_user.id,
                "recommendationId": recommendation_id,
            },
            order={"createdAt": "desc"},
        )
    except Exception as e:
        logger.error(f"[{user_id}] Failed to fetch training record: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process feedback. Please try again."
        )

    if not training_record:
        logger.warning(
            f"[{user_id}] No training record found for recommendation {recommendation_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No training record found for user {current_user.id} and recommendation {recommendation_id}"
        )
    
    # Update the found record with the new feedback
    try:
        await db.trainingrecord.update(
            where={"id": training_record.id},
            data={
                "liked": feedback.liked,
                "healthinessScore": feedback.healthinessScore,
                "tastinessScore": feedback.tastinessScore,
                "intentToTryScore": feedback.intentToTryScore,
            },
        )
        logger.debug(f"[{user_id}] Training record {training_record.id} updated with feedback")
    except Exception as e:
        logger.error(f"[{user_id}] Failed to update training record: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save feedback. Please try again."
        )

    # --- Version2: PHASE 4 - Check if feedback summarization should trigger ---
    # Count feedbacks since last summarization with robust error handling
    try:
        last_summary_time = current_user.feedbackSummaryLastUpdatedAt or datetime(1970, 1, 1)
        
        feedbacks_since_summary = await db.trainingrecord.count(
            where={
                "userId": current_user.id,
                "createdAt": {"gte": last_summary_time},
                "liked": {"not": None}  # Only count records with actual feedback
            }
        )
        
        logger.debug(
            f"[{user_id}] Feedback count since last summary: {feedbacks_since_summary} "
            f"(last summary: {last_summary_time})"
        )
        
        # If 5 or more feedbacks accumulated, trigger summarization
        if feedbacks_since_summary >= 5:
            logger.info(f"[{user_id}] Threshold reached ({feedbacks_since_summary} >= 5); triggering summarization")
            
            from tasks.recommendation_generator import trigger_feedback_summarization
            
            # Get the 5 recent feedbacks for summarization
            try:
                recent_feedbacks = await db.trainingrecord.find_many(
                    where={
                        "userId": current_user.id,
                        "createdAt": {"gte": last_summary_time},
                        "liked": {"not": None}
                    },
                    order={"createdAt": "desc"},
                    take=5
                )
                logger.debug(f"[{user_id}] Fetched {len(recent_feedbacks)} recent feedbacks for summarization")
            except Exception as e:
                logger.error(f"[{user_id}] Failed to fetch recent feedbacks: {str(e)}")
                recent_feedbacks = []
            
            # PHASE 4: Validate feedback list before summarization
            if recent_feedbacks:
                # Convert to format for summarization
                feedback_dicts = []
                for fb in recent_feedbacks:
                    feedback_dicts.append({
                        "recipe_name": fb.recommendationName,
                        "action": "liked" if fb.liked else "disliked",
                        "rating": fb.intentToTryScore,
                        "notes": None
                    })
                
                # Trigger async summarization (fire-and-forget)
                logger.info(f"[{user_id}] Fire-and-forget async summarization task created")
                asyncio.create_task(
                    trigger_feedback_summarization(current_user.id, feedback_dicts)
                )
            else:
                logger.warning(f"[{user_id}] Threshold met but no feedbacks to summarize")
        else:
            logger.debug(
                f"[{user_id}] Threshold not reached ({feedbacks_since_summary} < 5); "
                f"waiting for more feedback"
            )
    
    except Exception as e:
        logger.error(f"[{user_id}] Error in feedback summarization trigger: {str(e)}", exc_info=True)
        # Don't fail the user request - just log the error
        pass

    logger.info(f"[{user_id}] Feedback submitted successfully")
    
    # Refetch user to include any updated nextAllowedGenerationAt
    try:
        updated_user = await db.user.find_unique(where={"id": user_id})
        response = {
            "status": "success",
            "message": "Feedback received successfully."
        }
        if updated_user and updated_user.nextAllowedGenerationAt:
            response["nextAllowedGenerationAt"] = updated_user.nextAllowedGenerationAt.isoformat()
        return response
    except Exception as e:
        logger.warning(f"[{user_id}] Failed to refetch user for response: {str(e)}")
        return {"status": "success", "message": "Feedback received successfully."}