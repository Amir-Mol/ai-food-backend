import json
import pandas as pd
import numpy as np
import logging
import time
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, ValidationError, Field
from typing import List, Annotated, Dict, Any, Optional, Union

from ai_service_client import get_recipe_suggestion, ERROR_MESSAGE, AIUserProfile
from api.auth import get_current_active_user
from prisma.models import User
from recommender.engine import generate_consideration_set
from database import db

from config import PROCESSED_RECIPE_FILE, RECIPE_EMBEDDINGS_FILE

logger = logging.getLogger(__name__)

router = APIRouter()

# --- LOAD DATA ON STARTUP ---
try:
    print("Loading recipe data and embeddings for API...")
    # Use the paths from the central config file
    RECIPES_DF = pd.read_parquet(PROCESSED_RECIPE_FILE)
    RECIPE_EMBEDDINGS = np.load(RECIPE_EMBEDDINGS_FILE)
    
    # Set recipe_id as the index for fast lookups
    RECIPES_DF.set_index('recipe_id', inplace=True)
    
    print("Data and embeddings loaded successfully.")
except FileNotFoundError as e:
    print(f"FATAL ERROR: Could not load data files. {e}")
    RECIPES_DF = None
    RECIPE_EMBEDDINGS = None


# --- Pydantic Models for API Response ---

class NutritionalInfo(BaseModel):
    calories: Optional[float] = None
    protein: Optional[float] = None
    carbs: Optional[float] = None
    fat: Optional[float] = None
    sugars: Optional[float] = None
    sodium: Optional[float] = None

class FinalRankedRecommendation(BaseModel):
    recipeId: str
    name: str
    explanation: Optional[str] = None
    imageUrl: Optional[str] = None
    healthScore: Optional[float] = None
    ingredients: Optional[List[str]] = None
    recipeUrl: Optional[str] = None
    nutritionalInfo: Optional[NutritionalInfo] = None

class FinalRecommendationsResponse(BaseModel):
    recommendations: List[FinalRankedRecommendation]
    nextAllowedGenerationAt: Optional[datetime] = None

# --- Pydantic Models for AI Interaction ---

class AIOutputRecommendation(BaseModel):
    recipeId: Union[str, int]
    name: str
    explanation: str

class AIResponse(BaseModel):
    ranked_recommendations: List[AIOutputRecommendation]


@router.post("/generate-recommendations", tags=["AI Utilities"])
async def generate_recommendations(current_user: Annotated[User, Depends(get_current_active_user)]) -> Any:
    """
    Generate personalized recommendations (Stage 1 + Stage 2).
    
    PHASE 4 IMPROVEMENTS:
    - Enhanced timer gate with detailed error messages
    - Better logging and error tracking
    - Graceful handling of null/edge cases
    
    Flow:
    1. Check timer gate (nextAllowedGenerationAt)
    2. Get previously seen recipes (TrainingRecord)
    3. Generate fresh consideration set (Stage 1)
    4. Filter unseen recipes
    5. Call LLM for ranking (Stage 2)
    6. Enrich with metadata
    7. Save TrainingRecord for feedback collection
    """
    start_time = time.time()
    user_id = current_user.id
    
    logger.info(f"[{user_id}] Recommendation request started")
    
    if RECIPES_DF is None:
        logger.error(f"[{user_id}] Recipe data not loaded")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Recommendation data is not available. Please contact support."
        )
    
    # --- PHASE A STEP 5: Check experiment completion (cycle limit at 100) ---
    # Prevent further generation if user has reached 100 recommendations
    if current_user.isExperimentComplete or current_user.totalRecommendationsGenerated >= 100:
        logger.warning(
            f"[{user_id}] Experiment already complete: "
            f"{current_user.totalRecommendationsGenerated}/100 recommendations, "
            f"cycle {current_user.currentCycleNumber}/20"
        )
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Thank you for your participation! You have completed the recommendation experiment (100 recommendations). Your feedback has been valuable."
        )
    
    logger.debug(
        f"[{user_id}] Experiment progress: "
        f"{current_user.totalRecommendationsGenerated}/100 recommendations, "
        f"cycle {current_user.currentCycleNumber}/20"
    )
    
    # --- PHASE 4: Enhanced Timer Gate Check ---
    # Validates nextAllowedGenerationAt is in the future
    try:
        if current_user.nextAllowedGenerationAt and current_user.nextAllowedGenerationAt > datetime.now(timezone.utc):
            wait_seconds = (current_user.nextAllowedGenerationAt - datetime.now(timezone.utc)).total_seconds()
            wait_minutes = int(wait_seconds // 60)
            wait_seconds_remainder = int(wait_seconds % 60)
            
            detail_msg = f"Please wait {wait_minutes} minute{'s' if wait_minutes != 1 else ''}"
            if wait_seconds_remainder > 0:
                detail_msg += f" and {wait_seconds_remainder} second{'s' if wait_seconds_remainder != 1 else ''}"
            detail_msg += " before requesting new recommendations."
            
            logger.info(
                f"[{user_id}] Rate-limited: {wait_minutes}m {wait_seconds_remainder}s remaining. "
                f"Next allowed: {current_user.nextAllowedGenerationAt}"
            )
            
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=detail_msg
            )
    except HTTPException as he:
        # Re-raise the HTTPException (rate limit)
        raise he
    except Exception as e:
        logger.warning(f"[{user_id}] Unexpected error in timer gate: {str(e)}")
        # Continue if timer gate check fails (better UX than blocking)
    
    logger.debug(f"[{user_id}] Timer gate passed")
    
    # --- Get previously seen recipes ---
    try:
        feedback_entries = await db.trainingrecord.find_many(where={'userId': user_id})
        seen_recipe_ids = {f.recommendationId for f in feedback_entries}
        logger.debug(f"[{user_id}] Found {len(seen_recipe_ids)} previously seen recipes")
    except Exception as e:
        logger.error(f"[{user_id}] Failed to fetch feedback history: {str(e)}")
        seen_recipe_ids = set()  # Continue with empty set
    
    # --- Version2: ALWAYS generate fresh consideration set (no caching) ---
    try:
        user_profile_dict = current_user.model_dump()
        
        # PHASE 4: Feedback summary may be None for new users
        logger.debug(
            f"[{user_id}] Starting Stage 1: feedback summary "
            f"{'present' if current_user.feedbackSummaryForEmbedding else 'absent'}"
        )
        
        consideration_set = generate_consideration_set(
            user_profile=user_profile_dict,
            recipes_df=RECIPES_DF,
            recipe_embeddings=RECIPE_EMBEDDINGS,
            feedback_summary=current_user.feedbackSummaryForEmbedding
        )
        logger.debug(f"[{user_id}] Stage 1: Generated {len(consideration_set)} candidates")
    except Exception as e:
        logger.error(f"[{user_id}] Stage 1 failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to generate recipe candidates. Please try again."
        )
    
    # Filter unseen recipes
    final_consideration_set = [
        recipe for recipe in consideration_set 
        if str(recipe.get('recipeId')) not in seen_recipe_ids
    ]
    
    logger.debug(
        f"[{user_id}] Filtered: {len(consideration_set)} → "
        f"{len(final_consideration_set)} unseen recipes"
    )
    
    # --- Handle consideration set exhaustion ---    
    if not final_consideration_set:
        logger.warning(f"[{user_id}] No unseen recipes available")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You have seen all current recommendations. A new set will be ready on your next request."
        )

    # --- Create LLM-Optimized Payload ---
    llm_payload = [{
        "recipeId": rec.get("recipeId"),
        "name": rec.get("name"),
        "description": rec.get("description"),
        "ingredients": list(rec.get("ingredients", [])),
        "diets": list(rec.get("diets", [])),
        "healthScore": rec.get("healthScore")
    } for rec in final_consideration_set]
    
    # Build AIUserProfile for LLM
    user_profile_dict = current_user.model_dump()
    try:
        user_profile_for_ai = AIUserProfile.model_validate(user_profile_dict)
        logger.debug(f"[{user_id}] AIUserProfile built successfully")
    except ValidationError as e:
        logger.error(f"[{user_id}] Failed to build AIUserProfile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process user profile."
        )
    
    # PHASE 4: Handle null feedback summary for LLM
    if current_user.feedbackSummaryForLLM:
        user_profile_for_ai.feedbackSummaryForLLM = current_user.feedbackSummaryForLLM
        logger.debug(f"[{user_id}] LLM feedback summary attached ({len(current_user.feedbackSummaryForLLM)} chars)")
    else:
        logger.debug(f"[{user_id}] No LLM feedback summary (new user or first request)")
    
    # --- Call LLM for top 5 (Stage 2) ---
    logger.debug(f"[{user_id}] Starting Stage 2: LLM ranking {len(llm_payload)} candidates")
    try:
        suggestion = await get_recipe_suggestion(
            user_profile=user_profile_for_ai, 
            recipe_candidates=llm_payload
        )
    except Exception as e:
        logger.error(f"[{user_id}] Stage 2 LLM call failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service temporarily unavailable. Please try again."
        )
    
    if suggestion == ERROR_MESSAGE:
        logger.error(f"[{user_id}] LLM returned error message")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service unavailable."
        )
    
    logger.debug(f"[{user_id}] Stage 2: LLM response received")
    
    try:
        # --- Parse AI Response ---
        if suggestion.startswith("```json"):
            suggestion = suggestion.strip().replace("```json\n", "").replace("\n```", "")
        
        parsed_data = json.loads(suggestion)
        logger.debug(f"[{user_id}] LLM response parsed successfully")
        
        for item in parsed_data.get("ranked_recommendations", []):
            if "recipeId" in item:
                item["recipeId"] = str(item["recipeId"])
        
        ai_response = AIResponse.model_validate(parsed_data)
        logger.debug(f"[{user_id}] AIResponse validated: {len(ai_response.ranked_recommendations)} recommendations")
    except (json.JSONDecodeError, ValidationError) as e:
        logger.error(f"[{user_id}] Failed to parse LLM response: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"The AI service returned an invalid response. Error: {e}"
        )
    
    # --- Data Enrichment Step ---
    logger.debug(f"[{user_id}] Starting data enrichment")
    enriched_recommendations = []
    consideration_set_map = {str(rec['recipeId']): rec for rec in final_consideration_set}
    
    for ranked_rec in ai_response.ranked_recommendations:
        full_recipe_data = consideration_set_map.get(ranked_rec.recipeId)
        
        if full_recipe_data:
            is_control_group = current_user.group == "control"
            
            enriched_rec = FinalRankedRecommendation(
                recipeId=ranked_rec.recipeId,
                name=full_recipe_data.get("recipe_name"),
                explanation=None if is_control_group else ranked_rec.explanation,
                imageUrl=full_recipe_data.get("imageUrl"),
                healthScore=None if is_control_group else full_recipe_data.get("healthScore"),
                ingredients=full_recipe_data.get("ingredients"),
                recipeUrl=full_recipe_data.get("recipeUrl"),
                nutritionalInfo=NutritionalInfo(
                    calories=full_recipe_data.get("calories_per_100g [cal]"),
                    protein=full_recipe_data.get("protein_per_100g [g]"),
                    carbs=full_recipe_data.get("totalcarbohydrate_per_100g [g]"),
                    fat=full_recipe_data.get("totalfat_per_100g [g]"),
                    sugars=full_recipe_data.get("sugars_per_100g [g]"),
                    sodium=full_recipe_data.get("sodium_per_100g [mg]")
                )
            )
            enriched_recommendations.append(enriched_rec)
        else:
            logger.warning(f"[{user_id}] Recipe {ranked_rec.recipeId} not found in enrichment map")
    
    logger.debug(f"[{user_id}] Data enrichment complete: {len(enriched_recommendations)} recommendations enriched")
    
    # --- Save Training Records ---
    logger.debug(f"[{user_id}] Saving {len(enriched_recommendations)} training records")
    try:
        user_profile_snapshot_json = json.dumps(user_profile_for_ai.model_dump())
        saved_count = 0
        
        for rec in enriched_recommendations:
            try:
                await db.trainingrecord.create(
                    data={
                        "userId": current_user.id,
                        "userProfileSnapshot": user_profile_snapshot_json,
                        "recommendationId": str(rec.recipeId),
                        "recommendationName": rec.name,
                        "explanation": rec.explanation,
                        "group": current_user.group,
                    }
                )
                saved_count += 1
            except Exception as rec_error:
                logger.warning(f"[{user_id}] Failed to save record for recipe {rec.recipeId}: {str(rec_error)}")
                continue
        
        logger.info(f"[{user_id}] Saved {saved_count}/{len(enriched_recommendations)} training records")
    except Exception as e:
        logger.error(f"[{user_id}] Batch save error: {str(e)}")
        # Continue - don't fail the user request if we can't save records
    
    # Set timer for next generation (1 hour from now)
    next_allowed = datetime.now(timezone.utc) + timedelta(minutes=2)
    
    # --- PHASE A STEP 2: Track cycle progress ---
    # Calculate new totals for cycle tracking
    num_recommendations_generated = len(enriched_recommendations)
    new_total = current_user.totalRecommendationsGenerated + num_recommendations_generated
    new_cycle_number = new_total // 5  # 5 items per cycle
    is_experiment_complete = new_total >= 100
    
    logger.debug(
        f"[{user_id}] Cycle tracking: "
        f"generated {num_recommendations_generated}, "
        f"total {new_total}/100, "
        f"cycle {new_cycle_number}/20, "
        f"experiment_complete={is_experiment_complete}"
    )
    
    # Update user record with timer and cycle tracking
    try:
        await db.user.update(
            where={"id": user_id},
            data={
                "nextAllowedGenerationAt": next_allowed,
                "totalRecommendationsGenerated": new_total,
                "currentCycleNumber": new_cycle_number,
                "isExperimentComplete": is_experiment_complete
            }
        )
        logger.debug(f"[{user_id}] Timer set: next generation allowed at {next_allowed}")
        logger.info(f"[{user_id}] Cycle tracking updated: {new_total}/100 recommendations, cycle {new_cycle_number}/20")
    except Exception as e:
        logger.error(f"[{user_id}] Failed to update user with cycle tracking: {str(e)}")
        # Continue - don't fail request if update fails
    
    elapsed = time.time() - start_time
    logger.info(f"[{user_id}] Success: Generated {len(enriched_recommendations)} recommendations in {elapsed:.2f}s")
    
    return FinalRecommendationsResponse(
        recommendations=enriched_recommendations,
        nextAllowedGenerationAt=next_allowed
    )