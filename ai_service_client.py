import os
import logging
import asyncio
from functools import lru_cache
from typing import Any, Dict
from openai import AsyncAzureOpenAI, APIError
import json

from models.ai_profile import AIUserProfile

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ERROR_MESSAGE = "Sorry, I couldn't generate a recipe at this time. Please try again later."

@lru_cache
def get_azure_openai_client() -> AsyncAzureOpenAI:
    """
    Initializes and returns a singleton AsyncAzureOpenAI client.
    Reads credentials from AZURE_ environment variables.
    """
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")

    if not api_key or not endpoint:
        logger.critical("Azure OpenAI credentials (API_KEY or ENDPOINT) are missing.")
    
    return AsyncAzureOpenAI(
        api_key=api_key,
        api_version=api_version,
        azure_endpoint=endpoint
    )


# --- JSON Schema for Structured Outputs ---
RECOMMENDATION_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "ranked_recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "recipeId": {
                        "type": "string",
                        "description": "The original recipe ID from candidates"
                    },
                    "name": {
                        "type": "string",
                        "description": "The name of the recipe"
                    },
                    "explanation": {
                        "type": "string",
                        "description": "A balanced 4-5 sentence explanation covering taste, health, and drawbacks"
                    }
                },
                "required": ["recipeId", "name", "explanation"],
                "additionalProperties": False
            },
            "description": "Array of ranked recipe recommendations"
        }
    },
    "required": ["ranked_recommendations"],
    "additionalProperties": False
}

RANKING_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "ranked_recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rank": {"type": "integer"},
                    "recipeId": {"type": "string"},
                    "name": {"type": "string"},
                    "matched_preferences": {"type": "array", "items": {"type": "string"}},
                    "matched_health_factors": {"type": "array", "items": {"type": "string"}},
                    "negative_signals": {"type": "array", "items": {"type": "string"}},
                    "cautions": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["rank", "recipeId", "name", "matched_preferences", "matched_health_factors", "negative_signals", "cautions"],
                "additionalProperties": False
            }
        }
    },
    "required": ["ranked_recommendations"],
    "additionalProperties": False
}

EXPLANATION_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "final_recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rank": {"type": "integer"},
                    "recipeId": {"type": "string"},
                    "name": {"type": "string"},
                    "explanation": {"type": "string"}
                },
                "required": ["rank", "recipeId", "name", "explanation"],
                "additionalProperties": False
            }
        }
    },
    "required": ["final_recommendations"],
    "additionalProperties": False
}


async def _call_azure_openai_with_retry(
    client: AsyncAzureOpenAI,
    deployment_name: str,
    system_prompt: str,
    user_prompt: str,
    max_retries: int = 3,
    response_schema: dict | None = None,
    max_tokens: int = 2000
) -> str:
    """
    Helper function that calls Azure OpenAI with exponential backoff retry logic.
    
    Args:
        client: AsyncAzureOpenAI client instance
        deployment_name: Azure deployment name
        system_prompt: System prompt for the API
        user_prompt: User prompt for the API
        max_retries: Maximum number of retry attempts
        response_schema: Optional JSON schema for structured output enforcement
        max_tokens: Maximum tokens for the response
    
    Returns:
        The API response content or ERROR_MESSAGE if all retries fail
    """
    for attempt in range(max_retries):
        try:
            logger.info(f"[Attempt {attempt + 1}/{max_retries}] Calling Azure OpenAI API...")
            
            create_kwargs: Dict[str, Any] = {
                "model": deployment_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.7,
                "max_tokens": max_tokens,
            }
            if response_schema:
                create_kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "recipe_recommendations",
                        "schema": response_schema,
                        "strict": True
                    }
                }
            response = await client.chat.completions.create(**create_kwargs)
            
            suggestion = response.choices[0].message.content
            if suggestion:
                logger.info(f"[Attempt {attempt + 1}] API call successful!")
                return suggestion.strip()
            else:
                logger.warning(f"[Attempt {attempt + 1}] API returned empty content")
                
        except APIError as e:
            logger.warning(f"[Attempt {attempt + 1}] Azure OpenAI API error: {e}")
            
            # If this is the last attempt, return error message
            if attempt == max_retries - 1:
                logger.error(f"All {max_retries} retry attempts exhausted. Returning error.")
                return ERROR_MESSAGE
            
            # Tier 2: Exponential backoff (1s, 2s, 4s)
            wait_time = 2 ** attempt
            logger.info(f"[Attempt {attempt + 1}] Retrying in {wait_time}s...")
            await asyncio.sleep(wait_time)
            
        except Exception as e:
            logger.error(f"[Attempt {attempt + 1}] Unexpected error: {e}")
            
            # If this is the last attempt, return error message
            if attempt == max_retries - 1:
                logger.error(f"All {max_retries} retry attempts exhausted. Returning error.")
                return ERROR_MESSAGE
            
            # Exponential backoff
            wait_time = 2 ** attempt
            logger.info(f"[Attempt {attempt + 1}] Retrying in {wait_time}s...")
            await asyncio.sleep(wait_time)
    
    return ERROR_MESSAGE


# --- System Prompts for Two-Step LLM Pipeline ---

RANKING_SYSTEM_PROMPT = (
    "You are a ranking assistant for a personalized food recommender system.\n\n"
    "Your task is to re-rank a set of pre-filtered recipe candidates and select the top 5 "
    "recipes that best match the given user profile.\n\n"
    "All candidates have already passed mandatory dietary and allergy filters.\n"
    "Health scores are on a scale of 1 to 10, where 10 is the healthiest.\n\n"
    "You must use ONLY the provided information:\n"
    "- User profile (preferences, dietary needs, health conditions)\n"
    "- Feedback summary (previous likes/dislikes if available)\n"
    "- Recipe candidate profiles (name, ingredients, tags, health score)\n\n"
    "--------------------------------------------------\n"
    "RANKING CRITERIA\n"
    "--------------------------------------------------\n\n"
    "1. preference_score (positive alignment):\n"
    "   - How well the recipe matches liked ingredients, favorite cuisines, and positive feedback patterns\n\n"
    "2. negative_preference_penalty (soft penalty, not elimination):\n"
    "   - Reduce ranking if the recipe conflicts with disliked ingredients or negative feedback patterns\n"
    "   - Penalize proportionally — do NOT exclude candidates completely\n\n"
    "3. health_score_alignment:\n"
    "   - Prefer recipes with higher health scores for health-conscious users\n"
    "   - For users with specific conditions (e.g., Diabetes, High Blood Pressure), weight health score more heavily\n"
    "   - Consider relevant nutritional tags (e.g., Low Sugar, High Protein)\n\n"
    "--------------------------------------------------\n"
    "FINAL DECISION RULE\n"
    "--------------------------------------------------\n\n"
    "- preference_score and health_score_alignment are the most important factors\n"
    "- negative_preference_penalty reduces ranking but must NOT eliminate candidates\n"
    "- When multiple recipes score similarly, prefer diversity across cuisine, ingredients, or meal type\n\n"
    "--------------------------------------------------\n"
    "STRICT RULES\n"
    "--------------------------------------------------\n\n"
    "- Do NOT invent any recipe attributes or health properties\n"
    "- Do NOT use any external knowledge beyond what is provided\n"
    "- Do NOT generate explanations in this step\n"
    "- Return exactly 5 recipes\n"
)

EXPLANATION_SYSTEM_PROMPT = (
    "You are a personalized food recommendation assistant.\n\n"
    "Your task is to generate a short, personalized explanation for each of the pre-ranked recipes provided.\n\n"
    "You will be given the user's profile and structured signals for each recipe: "
    "matched preferences, health factors, negative signals, and cautions.\n\n"
    "--------------------------------------------------\n"
    "EXPLANATION OBJECTIVE\n"
    "--------------------------------------------------\n\n"
    "Each explanation should:\n"
    "1. Connect the recipe to the user's specific tastes and preferences\n"
    "2. Highlight relevant health aspects based on the provided health factors\n"
    "3. Gently mention any trade-offs or limitations from the cautions/negative signals\n"
    "4. Include a gentle, positive nudge encouraging the choice\n\n"
    "--------------------------------------------------\n"
    "NUDGING GUIDELINES\n"
    "--------------------------------------------------\n\n"
    "- Use positive and encouraging language\n"
    "- Do NOT be judgmental or forceful\n"
    "- Support user autonomy — the user should feel in control\n"
    "- Use soft suggestions such as 'this could be a good option if...', 'you might find this helpful for...'\n"
    "- Emphasize small, achievable improvements\n\n"
    "--------------------------------------------------\n"
    "FAITHFULNESS RULES\n"
    "--------------------------------------------------\n\n"
    "- Use ONLY the provided signals — do NOT invent facts\n"
    "- Do NOT make medical claims\n"
    "- If a benefit is not in matched_health_factors, do NOT mention it\n"
    "- If negative_signals or cautions are present, reflect them honestly but gently\n"
    "- Do NOT mention numerical health scores (e.g. 'health score of 5.1') — the app already shows a visual health bar to the user\n\n"
    "--------------------------------------------------\n"
    "STYLE REQUIREMENTS\n"
    "--------------------------------------------------\n\n"
    "- Address the user directly using 'you' and 'your'\n"
    "- Write 3-5 sentences per explanation\n"
    "- Keep a natural, friendly, and supportive tone\n"
    "- Avoid repetition across different recipe explanations\n"
)


async def get_recipe_suggestion(user_profile: AIUserProfile, recipe_candidates: list) -> str:
    """
    Generates recipe suggestions using a two-step LLM pipeline.

    Step 1 (Ranking): Re-ranks the candidates and selects top 5 with structured signals
                      (matched preferences, health factors, negative signals, cautions).
    Step 2 (Explanation): Generates personalized explanations grounded in Step 1's signals.

    Returns a JSON string with 'ranked_recommendations' matching the expected downstream format.
    Raises an Exception if Step 1 fails so the caller's retry logic can kick in.
    """
    client = get_azure_openai_client()
    deployment_name = os.getenv("AZURE_DEPLOYMENT_NAME", "gpt-4o-deployment")

    # Format inputs once — reused in both prompts
    user_profile_str = "\n".join([
        f"{key}: {json.dumps(value) if isinstance(value, (dict, list)) else value}"
        for key, value in user_profile.model_dump().items()
        if value is not None
    ])
    recipe_candidates_str = json.dumps(recipe_candidates, indent=2)

    # --- Step 1: Re-rank candidates and extract structured signals ---
    rank_user_prompt = f"""Here is the user's profile:
---USER PROFILE---
{user_profile_str}
------------------

Here are the recipe candidates to re-rank:
---RECIPE CANDIDATES---
{recipe_candidates_str}
-----------------------

Select the top 5 recipes that best match this user and return your ranking with structured signals."""

    logger.info("Stage 2 Step 1: Ranking recipe candidates...")
    rank_result_json = await _call_azure_openai_with_retry(
        client=client,
        deployment_name=deployment_name,
        system_prompt=RANKING_SYSTEM_PROMPT,
        user_prompt=rank_user_prompt,
        response_schema=RANKING_RESPONSE_SCHEMA,
        max_tokens=2000
    )

    if rank_result_json == ERROR_MESSAGE:
        raise Exception("Ranking LLM step failed after all retries")

    try:
        if rank_result_json.startswith("```json"):
            rank_result_json = rank_result_json.replace("```json", "").replace("```", "").strip()
        ranked_data = json.loads(rank_result_json)
        ranked_recipes = ranked_data.get("ranked_recommendations", [])
    except Exception as e:
        logger.error(f"Failed to parse ranking response: {e}")
        raise Exception(f"Ranking response parse error: {e}")

    if not ranked_recipes:
        raise Exception("Ranking step returned empty list")

    logger.info(f"Stage 2 Step 1 complete: {len(ranked_recipes)} recipes ranked")

    # --- Step 2: Generate personalized explanations from the structured signals ---
    ranked_recipes_str = json.dumps(ranked_recipes, indent=2)
    explain_user_prompt = f"""Here is the user's profile:
---USER PROFILE---
{user_profile_str}
------------------

Here are the top {len(ranked_recipes)} ranked recipes with their structured signals:
---RANKED RECIPES WITH SIGNALS---
{ranked_recipes_str}
---------------------------------

Generate a personalized explanation for each recipe using only the provided signals."""

    logger.info("Stage 2 Step 2: Generating personalized explanations...")
    explain_result_json = await _call_azure_openai_with_retry(
        client=client,
        deployment_name=deployment_name,
        system_prompt=EXPLANATION_SYSTEM_PROMPT,
        user_prompt=explain_user_prompt,
        response_schema=EXPLANATION_RESPONSE_SCHEMA,
        max_tokens=2000
    )

    explained_recipes = None
    if explain_result_json != ERROR_MESSAGE:
        try:
            if explain_result_json.startswith("```json"):
                explain_result_json = explain_result_json.replace("```json", "").replace("```", "").strip()
            explain_data = json.loads(explain_result_json)
            explained_recipes = explain_data.get("final_recommendations", [])
        except Exception as e:
            logger.error(f"Failed to parse explanation response: {e}")

    # Graceful degradation: if explanations fail, keep rankings with a placeholder
    if not explained_recipes:
        logger.warning("Explanation step failed; using ranked recipes with placeholder explanations")
        explained_recipes = [
            {
                "rank": r.get("rank", i + 1),
                "recipeId": r["recipeId"],
                "name": r["name"],
                "explanation": "Recommended based on your preferences and health profile."
            }
            for i, r in enumerate(ranked_recipes)
        ]

    logger.info(f"Stage 2 complete: {len(explained_recipes)} recommendations ready")

    # Return in the format expected by recommendation_generator.py
    result = {
        "ranked_recommendations": [
            {
                "recipeId": r["recipeId"],
                "name": r["name"],
                "explanation": r.get("explanation", "Recommended for you.")
            }
            for r in explained_recipes
        ]
    }
    return json.dumps(result)


async def summarize_feedback_history(
    previous_summary: dict | None,
    new_feedbacks: list,
    user_preferences: dict
) -> dict:
    """
    Uses LLM to synthesize feedback into two complementary summaries.
    
    This function creates:
    1. embedding_summary: 1-2 sentences for Stage 1 semantic search
    2. llm_summary: 3-5 sentences detailed for Stage 2 reasoning
    
    Takes previous summary + 5 new feedback items, iteratively updates.
    
    Args:
        previous_summary: Last computed summary dict with 'embedding_summary' and 'llm_summary' keys, or None if first time
        new_feedbacks: List of dicts with: {recipe_name, action, rating, notes}
        user_preferences: User profile dict for context (likedIngredients, favoriteCuisines, activityLevel)
    
    Returns:
        {
            "embedding_summary": str,  # ~1-2 sentences (~100 chars)
            "llm_summary": str,        # ~3-5 sentences (~300-400 chars)
            "feedback_count": int
        }
    
    Raises:
        Exception: If LLM call fails after retries
    """
    try:
        # Build feedback list for prompt — include all 3 scores for richer signal
        feedback_items = "\n".join([
            f"- {fb.get('recipe_name', 'Unknown')}: {fb.get('action', 'rated')} "
            f"(healthiness: {fb.get('healthinessScore', 'N/A')}/5, "
            f"tastiness: {fb.get('tastinessScore', 'N/A')}/5, "
            f"intent to try: {fb.get('intentToTryScore', 'N/A')}/5)"
            for fb in new_feedbacks
        ])
        
        previous_summary_text = "None (first time summarization)"
        if previous_summary:
            previous_summary_text = f"Embedding: {previous_summary.get('embedding_summary', 'N/A')}\nLLM: {previous_summary.get('llm_summary', 'N/A')}"
        
        likes_str = ', '.join(user_preferences.get('likedIngredients', []) or [])
        cuisines_str = ', '.join(user_preferences.get('favoriteCuisines', []) or [])
        activity = user_preferences.get('activityLevel', 'unknown')
        dietary_profile = user_preferences.get('dietaryProfile') or {}
        health_conditions = (dietary_profile.get('healthConditions') or {}).get('selected', [])
        health_str = ', '.join(health_conditions) if health_conditions else 'None'
        
        system_prompt = (
            "You are an expert nutritionist and chef analyzing user food preferences from feedback. "
            "Your task is to synthesize user feedback into two concise, distinct summaries: "
            "one optimized for vector embedding (semantic search), one for LLM reasoning. "
            "Be precise. Capture preference evolution. Avoid redundancy between the two summaries."
        )
        
        user_prompt = f"""Analyze this user's evolving food preferences and create 2 summaries.

PREVIOUS SUMMARY (if any):
{previous_summary_text}

NEW FEEDBACK (5 recent interactions — scores are out of 5):
{feedback_items}

USER BACKGROUND:
- Liked ingredients: {likes_str if likes_str else 'Not specified'}
- Preferred cuisines: {cuisines_str if cuisines_str else 'Not specified'}
- Activity level: {activity}
- Health conditions: {health_str}

CRITICAL INSTRUCTIONS:
1. EMBEDDING_SUMMARY (2-3 sentences, ~150-200 chars):
   - Written as a recipe-style description to match recipe document vocabulary
   - Use specific ingredient names, cuisine keywords, and dietary tags (e.g. High Protein, Low Sugar, Vegan)
   - Reflect both what the user liked AND disliked
   - Example style: "Liked: grilled chicken, pasta, Asian stir-fry, High Protein dishes. Disliked: heavy cream sauces, very spicy food. Prefers light, balanced meals."

2. LLM_SUMMARY (3-5 sentences, ~300-400 chars):
   - Detailed reasoning context for personalized recipe recommendations
   - Reference specific recipe types or dishes liked/disliked from feedback
   - Note if healthiness vs tastiness scores differ (e.g. user rates taste high but healthiness low — prefers flavour over nutrition)
   - Reference relevant health conditions if they affect recommendations
   - Capture preference evolution if evident across cycles

Return ONLY valid JSON:
{{
    "embedding_summary": "...",
    "llm_summary": "..."
}}"""
        
        client = get_azure_openai_client()
        deployment_name = os.getenv("AZURE_DEPLOYMENT_NAME", "gpt-4o-deployment")
        
        logger.info(f"[Feedback Summarization] Calling Azure OpenAI...")
        response = await client.chat.completions.create(
            model=deployment_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,  # Lower for consistent summarization
            max_tokens=1000,
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Handle markdown code blocks if present
        if response_text.startswith("```json"):
            response_text = response_text.replace("```json", "").replace("```", "").strip()
        
        result = json.loads(response_text)
        result["feedback_count"] = len(new_feedbacks)
        
        logger.info(f"[Feedback Summarization] Summary generated successfully")
        return result
        
    except Exception as e:
        logger.error(f"[Feedback Summarization] Error: {str(e)}")
        raise