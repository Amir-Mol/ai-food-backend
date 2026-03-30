"""
Background tasks for auto-generating recommendations.
Triggered after onboarding completion and after feedback cycles.
Runs asynchronously to avoid blocking user requests.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import logging
import json

from database import db
from recommender.engine import generate_consideration_set, RECIPES_DF, RECIPE_EMBEDDINGS
from ai_service_client import get_recipe_suggestion
from models.ai_profile import AIUserProfile
from config import CONSIDERATION_SET_SIZE

logger = logging.getLogger(__name__)


async def generate_and_save_recommendations(user_id: str) -> bool:
    """
    Generate personalized recommendations and save to user's profile.
    
    Flow:
    1. Update status to "generating"
    2. Generate fresh consideration set (Stage 1)
    3. Call LLM for top 5 (Stage 2)
    4. Save recommendations to user.recommendations
    5. Update status to "ready"
    6. Set nextAllowedGenerationAt = now + 1 hour
    
    Args:
        user_id: User ID to generate recommendations for
    
    Returns:
        bool: True if successful, False if failed
    """
    try:
        # Fetch user from database
        user = await db.user.find_unique(where={"id": user_id})
        if not user:
            logger.error(f"[{user_id}] User not found")
            return False
        
        # Update status
        await db.user.update(
            where={"id": user_id},
            data={"recommendationGenerationStatus": "generating"}
        )
        logger.info(f"[{user_id}] Status: generating")
        
        # Step 1: Generate consideration set (Stage 1)
        # Convert user profile fields to dict for engine
        user_profile = {
            "likedIngredients": user.likedIngredients or [],
            "dislikedIngredients": user.dislikedIngredients or [],
            "favoriteCuisines": user.favoriteCuisines or [],
            "activityLevel": user.activityLevel or "moderately active",
            "weight": user.weight,
            "height": user.height,
            "age": user.age,
            "gender": user.gender,
            "foodAllergies": user.foodAllergies or {},
            "dietaryProfile": user.dietaryProfile or {},
        }
        
        consideration_set = generate_consideration_set(
            user_profile=user_profile,
            recipes_df=RECIPES_DF,
            recipe_embeddings=RECIPE_EMBEDDINGS,
            consideration_set_size=CONSIDERATION_SET_SIZE,
            feedback_summary=user.feedbackSummaryForEmbedding  # Use feedback summary if available
        )
        logger.info(f"[{user_id}] Generated {len(consideration_set)} consideration set")
        
        # Filter out previously seen recipes
        feedback_entries = await db.trainingrecord.find_many(where={'userId': user_id})
        seen_recipe_ids = {f.recommendationId for f in feedback_entries}
        final_consideration_set = [
            recipe for recipe in consideration_set 
            if str(recipe.get('recipeId')) not in seen_recipe_ids
        ]
        
        if not final_consideration_set:
            logger.warning(f"[{user_id}] No unseen recipes in consideration set")
            await db.user.update(
                where={"id": user_id},
                data={"recommendationGenerationStatus": "idle"}
            )
            return False
        
        # Step 2: Create LLM payload
        llm_payload = [{
            "recipeId": rec.get("recipeId"),
            "name": rec.get("name"),
            "description": rec.get("description"),
            "ingredients": list(rec.get("ingredients", [])),
            "diets": list(rec.get("diets", [])),
            "healthScore": rec.get("healthScore")
        } for rec in final_consideration_set]
        
        # Step 3: Call LLM for top 5 (Stage 2)
        user_profile_dict = {
            "age": user.age,
            "gender": user.gender,
            "height": user.height,
            "weight": user.weight,
            "activityLevel": user.activityLevel,
            "dietaryProfile": user.dietaryProfile,
            "likedIngredients": user.likedIngredients,
            "dislikedIngredients": user.dislikedIngredients,
            "favoriteCuisines": user.favoriteCuisines,
            "feedbackSummaryForLLM": user.feedbackSummaryForLLM,
        }
        
        user_profile_for_ai = AIUserProfile.model_validate(user_profile_dict)
        
        suggestions_json = await get_recipe_suggestion(
            user_profile=user_profile_for_ai,
            recipe_candidates=llm_payload
        )
        logger.info(f"[{user_id}] LLM returned recommendations")
        
        # Parse LLM response
        if suggestions_json.startswith("```json"):
            suggestions_json = suggestions_json.replace("```json", "").replace("```", "").strip()
        
        suggestions_data = json.loads(suggestions_json)
        recommendations = suggestions_data.get("ranked_recommendations", [])
        
        logger.info(f"[{user_id}] Generated {len(recommendations)} recommendations")
        
        # Step 4: Save to database
        next_allowed = datetime.utcnow() + timedelta(hours=1)
        recommendations_json = json.dumps(recommendations)
        
        await db.user.update(
            where={"id": user_id},
            data={
                "recommendations": recommendations_json,  # Store as JSON
                "recommendationsReadyAt": datetime.utcnow(),
                "nextAllowedGenerationAt": next_allowed,
                "recommendationGenerationStatus": "ready"
            }
        )
        logger.info(f"[{user_id}] Status: ready. Next allowed: {next_allowed}")
        return True
        
    except Exception as e:
        logger.error(f"[{user_id}] Generation failed: {str(e)}")
        try:
            await db.user.update(
                where={"id": user_id},
                data={"recommendationGenerationStatus": "idle"}
            )
        except Exception as update_error:
            logger.error(f"[{user_id}] Failed to reset status: {str(update_error)}")
        return False


async def trigger_feedback_summarization(user_id: str, new_feedbacks: List[Dict[str, Any]]) -> bool:
    """
    Async trigger for feedback summarization pipeline.
    
    Checks if 5 feedbacks accumulated, calls LLM summarization, then triggers auto-generation.
    
    Args:
        user_id: User ID
        new_feedbacks: List of recent feedback dicts
    
    Returns:
        bool: True if summarization was triggered and succeeded
    """
    from ai_service_client import summarize_feedback_history
    
    try:
        user = await db.user.find_unique(where={"id": user_id})
        if not user:
            logger.error(f"[{user_id}] User not found for summarization")
            return False
        
        logger.info(f"[{user_id}] Summarizing {len(new_feedbacks)} feedbacks")
        
        # Update status to "summarizing"
        await db.user.update(
            where={"id": user_id},
            data={"recommendationGenerationStatus": "summarizing"}
        )
        
        # Call LLM summarization
        user_profile = {
            "likedIngredients": user.likedIngredients or [],
            "favoriteCuisines": user.favoriteCuisines or [],
            "activityLevel": user.activityLevel or "moderately active",
        }
        
        # Prepare previous summary if exists
        previous_summary = None
        if user.feedbackSummaryForEmbedding:
            previous_summary = {
                "embedding_summary": user.feedbackSummaryForEmbedding,
                "llm_summary": user.feedbackSummaryForLLM
            }
        
        summary_result = await summarize_feedback_history(
            previous_summary=previous_summary,
            new_feedbacks=new_feedbacks,
            user_preferences=user_profile
        )
        
        # Update user with new summaries
        await db.user.update(
            where={"id": user_id},
            data={
                "feedbackSummaryForEmbedding": summary_result["embedding_summary"],
                "feedbackSummaryForLLM": summary_result["llm_summary"],
                "feedbackSummaryLastUpdatedAt": datetime.utcnow()
            }
        )
        logger.info(f"[{user_id}] Summaries updated")
        
        # Auto-trigger new recommendation generation
        success = await generate_and_save_recommendations(user_id)
        
        if success:
            logger.info(f"[{user_id}] Feedback cycle complete: summarization + generation")
        else:
            logger.warning(f"[{user_id}] Generation failed after summarization")
        
        return success
        
    except Exception as e:
        logger.error(f"[{user_id}] Summarization failed: {str(e)}")
        try:
            await db.user.update(
                where={"id": user_id},
                data={"recommendationGenerationStatus": "idle"}
            )
        except Exception as reset_error:
            logger.error(f"[{user_id}] Failed to reset status: {str(reset_error)}")
        return False


async def trigger_recommendation_generation_on_onboarding(user_id: str) -> bool:
    """
    Trigger auto-generation of initial recommendations after onboarding.
    
    Called when user completes onboarding flow.
    
    Args:
        user_id: User ID
    
    Returns:
        bool: True if generation succeeded
    """
    logger.info(f"[{user_id}] Auto-generating recommendations post-onboarding")
    return await generate_and_save_recommendations(user_id)
