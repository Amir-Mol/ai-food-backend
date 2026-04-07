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
    recipeId: str  # Fixed: was "id", frontend expects "recipeId"
    name: str
    imageUrl: Optional[str] = "https://via.placeholder.com/300"  # Default image URL
    healthScore: int = Field(default=6, ge=0, le=20)  # Fixed: was "fsaHealthScore", frontend expects "healthScore"

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

@router.get("/")
async def get_recommendations(
    current_user: Annotated[User, Depends(get_current_active_user)],
    mealType: Optional[str] = None,
):
    """
    Returns pre-generated recommendations for the user.
    
    PHASE C STEP 1: Returns real recommendations stored in user.recommendations (JSON field)
    instead of generating fresh. Instant fetch for better UX.
    
    Flow:
    1. Check if user.recommendations exists and is not empty
    2. IF yes: Parse JSON and return recommendations
    3. IF no: Return status info (not ready or error)
    
    Note: mealType parameter is deprecated (not used for Prisma-based recommendations)
    """
    user_id = current_user.id
    logger.info(f"[{user_id}] GET /recommendations - Fetching pre-generated recommendations")
    
    try:
        # Check if recommendations are available
        if not current_user.recommendations:
            logger.warning(f"[{user_id}] No pre-generated recommendations found")
            
            # Return empty list with status
            return {
                "status": "no-recommendations",
                "showTransparencyFeatures": True,
                "recommendations": []
            }
        
        # Parse recommendations from JSON
        if isinstance(current_user.recommendations, str):
            try:
                recommendations_list = json.loads(current_user.recommendations)
            except json.JSONDecodeError as e:
                logger.error(f"[{user_id}] ❌ Failed to parse recommendations JSON: {str(e)}")
                return {
                    "status": "error",
                    "showTransparencyFeatures": True,
                    "recommendations": []
                }
        else:
            recommendations_list = current_user.recommendations if isinstance(current_user.recommendations, list) else []
        
        logger.debug(f"[{user_id}] Retrieved {len(recommendations_list)} pre-generated recommendations")
        
        # Convert to MealRecommendation format
        meal_recommendations = []
        for idx, rec in enumerate(recommendations_list):
            try:
                # Return ALL fields from the stored recommendation (not just 4)
                # The stored structure includes: recipeId, name, description, ingredients, healthScore, personalisedReason, etc.
                meal_rec = {
                    "recipeId": str(rec.get("recipeId", f"recipe_{idx}")),
                    "name": str(rec.get("name", f"Recipe {idx+1}")),
                    "explanation": str(rec.get("personalisedReason", "Recommended for you")),  # LLM explanation
                    "imageUrl": rec.get("imageUrl") or "https://via.placeholder.com/300",
                    "healthScore": max(0, min(20, int(rec.get("healthScore", 6)))),  # Clamp to 0-20
                    "ingredients": rec.get("ingredients", []) if isinstance(rec.get("ingredients"), list) else [],
                    "recipeUrl": str(rec.get("recipeUrl", "")),
                    "nutritionalInfo": rec.get("nutritionalInfo", {}),  # Pass through or empty
                }
                meal_recommendations.append(meal_rec)
            except Exception as e:
                logger.warning(f"[{user_id}] Failed to parse recommendation {idx}: {str(e)}, data: {rec}")
                continue
        
        logger.info(f"[{user_id}] ✅ Returning {len(meal_recommendations)} pre-generated recommendations")
        
        return {
            "status": "success",
            "showTransparencyFeatures": True,
            "recommendations": meal_recommendations
        }
        
    except Exception as e:
        logger.error(f"[{user_id}] ❌ Unexpected error in get_recommendations: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "showTransparencyFeatures": True,
            "recommendations": []
        }

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
    
    # PHASE C Step 10: Count feedbacks to help frontend detect 5th feedback
    # This allows frontend to auto-trigger next generation after 5th feedback
    feedbacks_count = feedbacks_since_summary  # Already counted above
    is_fifth_feedback = feedbacks_count >= 5
    logger.debug(
        f"[{user_id}] Feedback count check: {feedbacks_count} feedbacks "
        f"(is_fifth_feedback={is_fifth_feedback})"
    )
    
    # Refetch user to include any updated nextAllowedGenerationAt
    try:
        updated_user = await db.user.find_unique(where={"id": user_id})
        response = {
            "status": "success",
            "message": "Feedback received successfully."
        }
        if updated_user and updated_user.nextAllowedGenerationAt:
            response["nextAllowedGenerationAt"] = updated_user.nextAllowedGenerationAt.isoformat()
        
        # PHASE C Step 10: Add feedback counting info for frontend auto-trigger
        # feedbackCount: which feedback this is in the current cycle (1/5, 2/5, etc.)
        # isFifthFeedback: boolean flag so frontend can detect when to auto-trigger
        response["feedbackCount"] = feedbacks_count
        response["isFifthFeedback"] = is_fifth_feedback
        
        if is_fifth_feedback:
            logger.info(f"[{user_id}] ✅ 5th feedback reached - frontend should auto-trigger")
        
        return response
    except Exception as e:
        logger.warning(f"[{user_id}] Failed to refetch user for response: {str(e)}")
        # Return minimal response - don't break existing frontend code
        return {
            "status": "success",
            "message": "Feedback received successfully.",
            "feedbackCount": feedbacks_count,
            "isFifthFeedback": is_fifth_feedback
        }