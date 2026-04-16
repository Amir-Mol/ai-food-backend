"""
Background tasks for auto-generating recommendations.
Triggered after onboarding completion and after feedback cycles.
Runs asynchronously to avoid blocking user requests.

PHASE 4 ENHANCEMENTS:
- Comprehensive edge case handling (null summaries, concurrent requests)
- LLM failure recovery with graceful degradation
- Production-grade logging for CSC Rahti observability
- Retry logic with exponential backoff
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
import logging
import json
import time
import pandas as pd
import numpy as np

from database import db
from recommender.engine import generate_consideration_set
from ai_service_client import get_recipe_suggestion
from models.ai_profile import AIUserProfile
from config import CONSIDERATION_SET_SIZE, LLM_CANDIDATE_SIZE, PROCESSED_RECIPE_FILE, RECIPE_EMBEDDINGS_FILE

logger = logging.getLogger(__name__)

# Load recipe data and embeddings on module import
try:
    RECIPES_DF = pd.read_parquet(PROCESSED_RECIPE_FILE)
    RECIPES_DF.set_index('recipe_id', inplace=True)
    RECIPE_EMBEDDINGS = np.load(RECIPE_EMBEDDINGS_FILE)
    logger.info("Recipe data and embeddings loaded successfully")
except FileNotFoundError as e:
    logger.error(f"Failed to load recipe data: {e}")
    RECIPES_DF = None
    RECIPE_EMBEDDINGS = None

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0  # seconds
BACKOFF_MULTIPLIER = 2.0


async def _retry_llm_call(
    user_profile_for_ai: AIUserProfile,
    llm_payload: List[Dict[str, Any]],
    user_id: str,
    max_retries: int = MAX_RETRIES
) -> Optional[List[Dict[str, Any]]]:
    """
    Retry LLM call with exponential backoff.
    
    Args:
        user_profile_for_ai: AIUserProfile for LLM context
        llm_payload: Recipe candidates for ranking
        user_id: For logging
        max_retries: Max retry attempts
    
    Returns:
        List of ranked recommendations or None if all retries fail
    """
    backoff = INITIAL_BACKOFF
    
    for attempt in range(max_retries):
        try:
            logger.debug(f"[{user_id}] LLM call attempt {attempt + 1}/{max_retries}")
            
            suggestions_json = await get_recipe_suggestion(
                user_profile=user_profile_for_ai,
                recipe_candidates=llm_payload
            )
            
            # Parse LLM response
            if suggestions_json.startswith("```json"):
                suggestions_json = suggestions_json.replace("```json", "").replace("```", "").strip()
            
            suggestions_data = json.loads(suggestions_json)
            recommendations = suggestions_data.get("ranked_recommendations", [])
            
            logger.debug(f"[{user_id}] LLM returned {len(recommendations)} recommendations")
            return recommendations
            
        except Exception as e:
            logger.warning(
                f"[{user_id}] LLM call failed (attempt {attempt + 1}): {str(e)}"
            )
            
            if attempt < max_retries - 1:
                await asyncio.sleep(backoff)
                backoff *= BACKOFF_MULTIPLIER
            else:
                logger.error(f"[{user_id}] LLM failed after {max_retries} attempts")
                return None


async def generate_and_save_recommendations(user_id: str) -> bool:
    """
    Generate personalized recommendations and save to user's profile.
    
    PHASE 4 IMPROVEMENTS:
    - Handles null feedback summaries gracefully (new users)
    - Graceful degradation if LLM fails (skips Stage 2, continues)
    - Comprehensive logging for observability
    - Proper error recovery and status reset
    
    Flow:
    1. Fetch user, validate exists
    2. Update status to "generating"
    3. Generate fresh consideration set (Stage 1)
    4. Filter out previously seen recipes
    5. Call LLM for top 5 (Stage 2) with retry logic
    6. Fallback to Stage 1 results if LLM fails
    7. Save recommendations to user.recommendations
    8. Update status to "ready"
    9. Set nextAllowedGenerationAt = now + 1 hour
    
    Args:
        user_id: User ID to generate recommendations for
    
    Returns:
        bool: True if successful, False if failed
    """
    start_time = time.time()
    try:
        # Fetch user from database
        user = await db.user.find_unique(where={"id": user_id})
        if not user:
            logger.error(f"[{user_id}] User not found in database")
            return False
        
        # --- PHASE A STEP 5: Check experiment completion (cycle limit at 100) ---
        # Prevent generation if user has already reached 100 recommendations
        if user.isExperimentComplete or user.totalRecommendationsGenerated >= 100:
            logger.warning(
                f"[{user_id}] Experiment already complete: "
                f"{user.totalRecommendationsGenerated}/100 recommendations, "
                f"cycle {user.currentCycleNumber}/20. Skipping generation."
            )
            # Reset status so frontend stops polling (was set to "summarizing" by trigger_feedback_summarization)
            try:
                await db.user.update(
                    where={"id": user_id},
                    data={"recommendationGenerationStatus": "idle"}
                )
            except Exception as e:
                logger.warning(f"[{user_id}] Could not reset status after experiment-complete skip: {str(e)}")
            return False
        
        logger.info(f"[{user_id}] Starting recommendation generation")
        logger.debug(
            f"[{user_id}] Current progress: "
            f"{user.totalRecommendationsGenerated}/100 recommendations, "
            f"cycle {user.currentCycleNumber}/20"
        )
        
        # Update status to "generating"
        await db.user.update(
            where={"id": user_id},
            data={"recommendationGenerationStatus": "generating"}
        )
        logger.debug(f"[{user_id}] Status updated to: generating")
        
        # PHASE 4: Handle null feedback summary gracefully
        feedback_summary = user.feedbackSummaryForEmbedding
        if feedback_summary:
            logger.debug(f"[{user_id}] Using feedback summary ({len(feedback_summary)} chars)")
        else:
            logger.debug(f"[{user_id}] No feedback summary (new user or first generation)")
        
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
            "dietaryProfile": user.dietaryProfile or {},
        }
        
        # Step 2: Fetch seen recipe IDs (used by Stage 1 to pre-filter before scoring)
        try:
            feedback_entries = await db.trainingrecord.find_many(where={'userId': user_id})
            seen_recipe_ids = {f.recommendationId for f in feedback_entries}
            logger.debug(f"[{user_id}] Found {len(seen_recipe_ids)} previously seen recipes to exclude")
        except Exception as e:
            logger.error(f"[{user_id}] Failed to fetch seen recipes: {str(e)}")
            await db.user.update(
                where={"id": user_id},
                data={"recommendationGenerationStatus": "idle"}
            )
            return False

        # Extract liked and disliked recipe names from feedback history for richer embedding document
        liked_recipe_names = [
            f.recommendationName for f in feedback_entries
            if f.liked is True and f.recommendationName
        ]
        disliked_recipe_names = [
            f.recommendationName for f in feedback_entries
            if f.liked is False and f.recommendationName
        ]
        logger.debug(f"[{user_id}] Found {len(liked_recipe_names)} liked and {len(disliked_recipe_names)} disliked recipes for embedding enrichment")

        try:
            consideration_set = generate_consideration_set(
                user_profile=user_profile,
                recipes_df=RECIPES_DF,
                recipe_embeddings=RECIPE_EMBEDDINGS,
                consideration_set_size=CONSIDERATION_SET_SIZE,
                feedback_summary=feedback_summary,  # May be None for new users
                seen_recipe_ids=seen_recipe_ids,     # Excluded before scoring
                liked_recipe_names=liked_recipe_names or None,   # None if empty list
                disliked_recipe_names=disliked_recipe_names or None  # None if empty list
            )
            logger.debug(f"[{user_id}] Stage 1: Generated {len(consideration_set)} candidates")
        except Exception as e:
            logger.error(f"[{user_id}] Stage 1 failed: {str(e)}")
            await db.user.update(
                where={"id": user_id},
                data={"recommendationGenerationStatus": "idle"}
            )
            return False

        final_consideration_set = consideration_set
        if not final_consideration_set:
            logger.warning(f"[{user_id}] No unseen recipes in consideration set")
            await db.user.update(
                where={"id": user_id},
                data={"recommendationGenerationStatus": "idle"}
            )
            return False
        
        # Step 3: Create LLM payload — trim to top LLM_CANDIDATE_SIZE (already ranked by Stage 1 score)
        llm_payload = [{
            "recipeId": rec.get("recipeId"),
            "name": rec.get("name"),
            "ingredients": list(rec.get("ingredients", [])),
            "tags": list(rec.get("tags", [])),
            "healthScore": rec.get("healthScore")
        } for rec in final_consideration_set[:LLM_CANDIDATE_SIZE]]
        
        # Step 4: Build AIUserProfile for Stage 2
        # PHASE 4: Handle null feedback summary for LLM
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
            "feedbackSummaryForLLM": user.feedbackSummaryForLLM,  # May be None
        }
        
        try:
            user_profile_for_ai = AIUserProfile.model_validate(user_profile_dict)
        except Exception as e:
            logger.error(f"[{user_id}] Failed to build AIUserProfile: {str(e)}")
            await db.user.update(
                where={"id": user_id},
                data={"recommendationGenerationStatus": "idle"}
            )
            return False
        
        # Step 5: Call LLM for top 5 (Stage 2) with retry logic
        # PHASE 4: Graceful degradation if LLM fails
        logger.debug(f"[{user_id}] Stage 2: Starting LLM ranking")
        
        recommendations = await _retry_llm_call(
            user_profile_for_ai=user_profile_for_ai,
            llm_payload=llm_payload,
            user_id=user_id,
            max_retries=MAX_RETRIES
        )
        
        if not recommendations:
            logger.warning(f"[{user_id}] LLM failed; falling back to Stage 1 results (top 5)")
            # PHASE 4: Fallback to top 5 from Stage 1 if LLM fails
            recommendations = [
                {
                    "recipeId": rec.get("recipeId"),
                    "name": rec.get("name"),
                    "relevanceScore": 0.8,  # Placeholder
                    "personalisedReason": "Recommended based on your preferences",
                    "healthScore": rec.get("healthScore", 0)
                }
                for rec in final_consideration_set[:5]
            ]
        else:
            logger.debug(f"[{user_id}] Stage 2: LLM ranked {len(recommendations)} recommendations")
        
        # Step 5.5: ENRICHMENT - Add missing fields from recipe database
        # This mirrors the POST endpoint's enrichment step to ensure consistency
        logger.debug(f"[{user_id}] Starting data enrichment for {len(recommendations)} recommendations")
        enriched_recommendations = []
        consideration_set_map = {str(rec['recipeId']): rec for rec in final_consideration_set}
        
        for rec in recommendations:
            recipe_id = str(rec.get('recipeId'))
            full_recipe_data = consideration_set_map.get(recipe_id)
            
            if full_recipe_data:
                # Enrich with full recipe data
                enriched_rec = {
                    "recipeId": recipe_id,
                    "name": rec.get("name", full_recipe_data.get("name")),
                    "personalisedReason": rec.get("explanation") or rec.get("personalisedReason") or "Recommended for you",
                    "imageUrl": full_recipe_data.get("imageUrl"),
                    "healthScore": full_recipe_data.get("healthScore", 6),
                    "ingredients": full_recipe_data.get("ingredients", []),
                    "recipeUrl": full_recipe_data.get("recipeUrl"),
                    "nutritionalInfo": {
                        "calories": full_recipe_data.get("calories_per_100g [cal]"),
                        "protein": full_recipe_data.get("protein_per_100g [g]"),
                        "carbs": full_recipe_data.get("totalcarbohydrate_per_100g [g]"),
                        "fat": full_recipe_data.get("totalfat_per_100g [g]"),
                        "sugars": full_recipe_data.get("sugars_per_100g [g]"),
                        "sodium": full_recipe_data.get("sodium_per_100g [mg]")
                    }
                }
                enriched_recommendations.append(enriched_rec)
            else:
                logger.warning(f"[{user_id}] Recipe {recipe_id} not found in enrichment map, using lean data")
                # Fallback to lean data if recipe not found
                enriched_recommendations.append(rec)
        
        logger.debug(f"[{user_id}] Data enrichment complete: {len(enriched_recommendations)} recommendations enriched")
        
        # Step 5.6: CREATE TRAINING RECORDS
        # This ensures feedback submission will find matching records
        logger.debug(f"[{user_id}] Creating {len(enriched_recommendations)} training records")
        try:
            user_profile_snapshot_json = json.dumps(user_profile_for_ai.model_dump())
            saved_count = 0
            
            for rec in enriched_recommendations:
                try:
                    await db.trainingrecord.create(
                        data={
                            "userId": user.id,
                            "userProfileSnapshot": user_profile_snapshot_json,
                            "recommendationId": str(rec.get("recipeId")),
                            "recommendationName": rec.get("name"),
                            "explanation": rec.get("personalisedReason"),
                            "group": user.group,
                        }
                    )
                    saved_count += 1
                except Exception as rec_error:
                    logger.warning(f"[{user_id}] Failed to create record for recipe {rec.get('recipeId')}: {str(rec_error)}")
                    continue
            
            logger.info(f"[{user_id}] Created {saved_count}/{len(enriched_recommendations)} training records")
        except Exception as e:
            logger.error(f"[{user_id}] Batch training record creation error: {str(e)}")
            # Continue - don't fail if we can't save training records
        
        # Step 6: Save to database
        # Do NOT set nextAllowedGenerationAt here - it's set AFTER 5th feedback in api/recommendations.py
        # This ensures first cycle shows "Find a Meal" button, not a timer
        recommendations_json = json.dumps(enriched_recommendations)
        
        # --- PHASE A STEP 2: Track cycle progress ---
        # Use enriched_recommendations count (what was actually saved), capped at 5 to prevent drift
        num_recommendations_generated = min(len(enriched_recommendations), 5)
        new_total = user.totalRecommendationsGenerated + num_recommendations_generated
        new_cycle_number = new_total // 5  # 5 items per cycle
        is_experiment_complete = new_total >= 100
        
        logger.debug(
            f"[{user_id}] Cycle tracking: "
            f"generated {num_recommendations_generated}, "
            f"total {new_total}/100, "
            f"cycle {new_cycle_number}/20, "
            f"experiment_complete={is_experiment_complete}"
        )
        
        try:
            await db.user.update(
                where={"id": user_id},
                data={
                    "recommendations": recommendations_json,  # Store as JSON
                    "recommendationsReadyAt": datetime.now(timezone.utc),
                    "recommendationGenerationStatus": "ready",
                    "totalRecommendationsGenerated": new_total,
                    "currentCycleNumber": new_cycle_number,
                    "isExperimentComplete": is_experiment_complete
                    # NOTE: nextAllowedGenerationAt NOT set here - set after 5th feedback instead
                }
            )
            elapsed = time.time() - start_time
            logger.info(
                f"[{user_id}] Success: Generated {len(recommendations)} recommendations "
                f"in {elapsed:.2f}s. Cycle {new_cycle_number}/20, Total {new_total}/100. Rate limit will be set after 5th feedback."
            )
            return True
            
        except Exception as e:
            logger.error(f"[{user_id}] Failed to save recommendations: {str(e)}")
            await db.user.update(
                where={"id": user_id},
                data={"recommendationGenerationStatus": "idle"}
            )
            return False
        
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[{user_id}] Generation failed after {elapsed:.2f}s: {str(e)}", exc_info=True)
        try:
            await db.user.update(
                where={"id": user_id},
                data={"recommendationGenerationStatus": "idle"}
            )
        except Exception as reset_error:
            logger.error(f"[{user_id}] Failed to reset status after error: {str(reset_error)}")
        return False


async def trigger_feedback_summarization(user_id: str, new_feedbacks: List[Dict[str, Any]]) -> bool:
    """
    Async trigger for feedback summarization pipeline.
    
    PHASE 4 IMPROVEMENTS:
    - Handles concurrent feedback submissions safely
    - Empty feedback list validation
    - Better error handling and fallbacks
    - Comprehensive logging
    
    Args:
        user_id: User ID
        new_feedbacks: List of recent feedback dicts
    
    Returns:
        bool: True if summarization was triggered and succeeded
    """
    from ai_service_client import summarize_feedback_history
    
    start_time = time.time()
    
    try:
        # PHASE 4: Validate input
        if not new_feedbacks:
            logger.warning(f"[{user_id}] Summarization called with empty feedback list")
            return False
        
        logger.info(f"[{user_id}] Starting feedback summarization ({len(new_feedbacks)} feedbacks)")
        
        user = await db.user.find_unique(where={"id": user_id})
        if not user:
            logger.error(f"[{user_id}] User not found for summarization")
            return False
        
        # PHASE 4: Handle concurrent requests - check current status
        if user.recommendationGenerationStatus in ["summarizing", "generating"]:
            logger.warning(
                f"[{user_id}] Already {user.recommendationGenerationStatus}; "
                f"skipping concurrent summarization request"
            )
            return False
        
        # Reset submission counter NOW — before any potentially-failing work.
        # If summarization fails below, the counter is already 0 so the next
        # batch of 5 feedbacks (not the very next single feedback) will re-trigger.
        try:
            await db.user.update(
                where={"id": user_id},
                data={"feedbackSubmissionCount": 0}
            )
            logger.debug(f"[{user_id}] feedbackSubmissionCount reset to 0 (pre-summarization)")
        except Exception as e:
            logger.warning(f"[{user_id}] Failed to reset submission counter early: {str(e)}")
            # Continue — don't abort summarization just because counter reset failed
        
        # Update status to "summarizing"
        await db.user.update(
            where={"id": user_id},
            data={"recommendationGenerationStatus": "summarizing"}
        )
        logger.debug(f"[{user_id}] Status updated to: summarizing")
        
        # Build user profile for summarization context
        user_profile = {
            "likedIngredients": user.likedIngredients or [],
            "favoriteCuisines": user.favoriteCuisines or [],
            "activityLevel": user.activityLevel or "moderately active",
            "dietaryProfile": user.dietaryProfile or {},  # Provides health conditions for context
        }
        
        # PHASE 4: Prepare previous summary if exists (handle null gracefully)
        previous_summary = None
        if user.feedbackSummaryForEmbedding and user.feedbackSummaryForLLM:
            previous_summary = {
                "embedding_summary": user.feedbackSummaryForEmbedding,
                "llm_summary": user.feedbackSummaryForLLM
            }
            logger.debug(f"[{user_id}] Using previous summary from {user.feedbackSummaryLastUpdatedAt}")
        else:
            logger.debug(f"[{user_id}] First summarization for this user")
        
        # Call LLM summarization
        try:
            summary_result = await summarize_feedback_history(
                previous_summary=previous_summary,
                new_feedbacks=new_feedbacks,
                user_preferences=user_profile
            )
            logger.debug(f"[{user_id}] LLM summarization successful")
        except Exception as e:
            logger.error(f"[{user_id}] LLM summarization failed: {str(e)}")
            await db.user.update(
                where={"id": user_id},
                data={"recommendationGenerationStatus": "idle"}
            )
            return False
        
        # Update user with new summaries
        try:
            await db.user.update(
                where={"id": user_id},
                data={
                    "feedbackSummaryForEmbedding": summary_result["embedding_summary"],
                    "feedbackSummaryForLLM": summary_result["llm_summary"],
                    "feedbackSummaryLastUpdatedAt": datetime.now(timezone.utc),
                    # feedbackSubmissionCount already reset to 0 at task start
                }
            )
            logger.debug(f"[{user_id}] Summaries saved to database")
        except Exception as e:
            logger.error(f"[{user_id}] Failed to save summaries: {str(e)}")
            await db.user.update(
                where={"id": user_id},
                data={"recommendationGenerationStatus": "idle"}
            )
            return False
        
        # Auto-trigger new recommendation generation
        logger.debug(f"[{user_id}] Auto-triggering recommendation generation")
        success = await generate_and_save_recommendations(user_id)
        
        elapsed = time.time() - start_time
        if success:
            logger.info(
                f"[{user_id}] Success: Feedback cycle complete "
                f"(summarization + generation in {elapsed:.2f}s)"
            )
        else:
            logger.warning(
                f"[{user_id}] Summarization OK but generation failed "
                f"(elapsed: {elapsed:.2f}s)"
            )
        
        return success
        
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(
            f"[{user_id}] Summarization failed after {elapsed:.2f}s: {str(e)}", 
            exc_info=True
        )
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
    Wrapper that logs onboarding context.
    
    Args:
        user_id: User ID
    
    Returns:
        bool: True if generation succeeded
    """
    logger.info(f"[{user_id}] Onboarding complete; auto-generating initial recommendations")
    return await generate_and_save_recommendations(user_id)
