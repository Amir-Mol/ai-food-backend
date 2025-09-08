import json
import pandas as pd
import numpy as np
import logging
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, ValidationError, Field
from typing import List, Annotated, Dict, Any, Optional, Union

from ai_service_client import get_recipe_suggestion, ERROR_MESSAGE, AIUserProfile
from api.auth import get_current_active_user
from prisma.models import User
from recommender.engine import generate_consideration_set
from database import db

from config import PROCESSED_RECIPE_FILE, RECIPE_EMBEDDINGS_FILE


router = APIRouter()

# --- Simple In-Memory Cache ---
CONSIDERATION_SET_CACHE = {}

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

# --- Pydantic Models for AI Interaction ---

class AIOutputRecommendation(BaseModel):
    recipeId: Union[str, int]
    name: str
    explanation: str

class AIResponse(BaseModel):
    ranked_recommendations: List[AIOutputRecommendation]


@router.post("/generate-recommendations", tags=["AI Utilities"])
async def generate_recommendations(current_user: Annotated[User, Depends(get_current_active_user)]) -> Any:
    if RECIPES_DF is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Recommendation data is not available. Please contact support."
        )

    user_id = current_user.id
    feedback_entries = await db.trainingrecord.find_many(where={'userId': user_id})
    seen_recipe_ids = {f.recommendationId for f in feedback_entries}

    if user_id in CONSIDERATION_SET_CACHE:
        print(f"Cache HIT for user {user_id}")
        consideration_set = CONSIDERATION_SET_CACHE[user_id]
    else:
        print(f"Cache MISS for user {user_id}")
        user_profile_dict = current_user.model_dump()
        consideration_set = generate_consideration_set(user_profile=user_profile_dict, recipes_df=RECIPES_DF, recipe_embeddings=RECIPE_EMBEDDINGS)
        CONSIDERATION_SET_CACHE[user_id] = consideration_set

    final_consideration_set = [recipe for recipe in consideration_set if str(recipe.get('recipeId')) not in seen_recipe_ids]
    
    # --- Handle consideration set exhaustion ---    
    if not final_consideration_set:
        # If the user has seen all recipes, invalidate the cache and tell them to try again.
        if user_id in CONSIDERATION_SET_CACHE:
            del CONSIDERATION_SET_CACHE[user_id]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You have seen all current recommendations. A new set will be ready on your next request."
        )

    # --- Create LLM-Optimized Payload ---
    llm_payload = [{
        "recipeId": rec.get("recipeId"),
        "name": rec.get("name"),
        "description": rec.get("description"),
        "ingredients": list(rec.get("ingredients", [])),  # Convert to list
        "diets": list(rec.get("diets", [])),          # Convert to list
        "healthScore": rec.get("healthScore")
    } for rec in final_consideration_set]
    # --- End ---

    user_profile_dict = current_user.model_dump()
    user_profile_for_ai = AIUserProfile.model_validate(user_profile_dict)

    suggestion = await get_recipe_suggestion(user_profile=user_profile_for_ai, recipe_candidates=llm_payload)

    if suggestion == ERROR_MESSAGE:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI service unavailable.")

    try:
        # --- Parse AI Response ---
        if suggestion.startswith("```json"):
            suggestion = suggestion.strip().replace("```json\n", "").replace("\n```", "")
        parsed_data = json.loads(suggestion)
        
        for item in parsed_data.get("ranked_recommendations", []):
            if "recipeId" in item:
                item["recipeId"] = str(item["recipeId"])
        
        ai_response = AIResponse.model_validate(parsed_data)
        # --- End Parsing ---

        # --- Data Enrichment Step ---
        enriched_recommendations = []
        # Create a lookup map from the full consideration set for efficiency
        consideration_set_map = {str(rec['recipeId']): rec for rec in final_consideration_set}

        for ranked_rec in ai_response.ranked_recommendations:
            full_recipe_data = consideration_set_map.get(ranked_rec.recipeId)
            
            if full_recipe_data:
                # Control what data is shown based on user group for experiment
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
                        calories=full_recipe_data.get("calories_per_serving [cal]"),
                        protein=full_recipe_data.get("protein_per_serving [g]"),
                        carbs=full_recipe_data.get("totalcarbohydrate_per_serving [g]"),
                        fat=full_recipe_data.get("totalfat_per_serving [g]"),
                        sugars=full_recipe_data.get("sugars_per_serving [g]"),
                        sodium=full_recipe_data.get("sodium_per_serving [mg]")
                    )
                )
                enriched_recommendations.append(enriched_rec)
        # --- End Enrichment ---

        # loops through your final enriched_recommendations list and saves a detailed record for each one to the database
        try:
            # Convert the Pydantic model to a dictionary, then to a JSON string
            user_profile_snapshot_json = json.dumps(user_profile_for_ai.model_dump())
            for rec in enriched_recommendations:
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
        except Exception as e:
            # In a production environment, you would want to log this error
            # without failing the user's request.
            print(f"Warning: Could not save training record. Error: {e}")

        return FinalRecommendationsResponse(recommendations=enriched_recommendations)
    
        # This line is for debug pupose:
        #return final_consideration_set

    except (json.JSONDecodeError, ValidationError) as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"The AI service returned an invalid response. Error: {e}"
        )