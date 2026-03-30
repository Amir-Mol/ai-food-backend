import os
import logging
import asyncio
from functools import lru_cache
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


async def _call_azure_openai_with_retry(
    client: AsyncAzureOpenAI,
    deployment_name: str,
    system_prompt: str,
    user_prompt: str,
    max_retries: int = 3
) -> str:
    """
    Helper function that calls Azure OpenAI with exponential backoff retry logic.
    
    Args:
        client: AsyncAzureOpenAI client instance
        deployment_name: Azure deployment name
        system_prompt: System prompt for the API
        user_prompt: User prompt for the API
        max_retries: Maximum number of retry attempts
    
    Returns:
        The API response content or ERROR_MESSAGE if all retries fail
    """
    for attempt in range(max_retries):
        try:
            logger.info(f"[Attempt {attempt + 1}/{max_retries}] Calling Azure OpenAI API...")
            
            response = await client.chat.completions.create(
                model=deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=1500,
                # Tier 1: Structured Outputs - enforce schema server-side
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "recipe_recommendations",
                        "schema": RECOMMENDATION_RESPONSE_SCHEMA,
                        "strict": True
                    }
                }
            )
            
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


async def get_recipe_suggestion(user_profile: AIUserProfile, recipe_candidates: list):
    """
    Generates recipe suggestions using Azure OpenAI with Structured Outputs and retry logic.
    
    Tier 1 (Primary): Uses Structured Outputs to enforce schema validation server-side.
    Tier 2 (Fallback): Uses exponential backoff retry logic if the API call fails.
    """
    # Convert the user profile and candidates to a string format for the prompt
    user_profile_str = "\n".join([f"{key}: {value}" for key, value in user_profile.model_dump().items() if value])
    recipe_candidates_str = json.dumps(recipe_candidates, indent=2)

    # System prompt: role, rules, constraints
    system_prompt = (
        "You are an expert nutritionist and chef. "
        "Your task is to analyze a user's profile and a list of candidate recipes. "
        "You must re-rank the candidates and return the top 5 that best fit. "
        "For each of the top 5, write a concise and helpful explanation of about 4-5 sentences. The explanation paragraph must be balanced: \n"
        "- Start with why it matches the user's tastes and preferences.\n"
        "- Then, discuss its health aspects in the context of the user's profile.\n"
        "- Finally, mention any potential drawbacks or considerations.\n"
        "Strict rules:\n"
        "- Do NOT invent new recipes. The number of recipes you return must not be more than the number of candidates provided.\n"
        "- Return no more recipes than the number of candidates provided.\n"
        "- Always include the original recipeId exactly as given.\n"
        "- All explanations MUST be personalized based on the user's profile.\n"
        "- Address the user directly in the second person ('you', 'your').\n"
        "- Output ONLY valid JSON matching the specified schema."
    )

    # User prompt: inputs + schema info
    user_prompt = f"""
    Here is the user's profile:
    ---USER PROFILE---
    {user_profile_str}
    ------------------

    Here is the list of recipe candidates:
    ---RECIPE CANDIDATES---
    {recipe_candidates_str}
    -----------------------

    Now return the final ranked recommendations in this exact JSON structure:

    {{
      "ranked_recommendations": [
        {{
          "recipeId": "original_recipe_id_from_candidates",
          "name": "Recipe Name Here",
          "explanation": "This is a balanced, 4-5 sentence explanation paragraph that covers taste, health, and drawbacks."
        }}
      ]
    }}    
    """

    client = get_azure_openai_client()
    deployment_name = os.getenv("AZURE_DEPLOYMENT_NAME", "gpt-4o-deployment")

    # Call Azure OpenAI with Structured Outputs (Tier 1) and Retry Logic (Tier 2)
    return await _call_azure_openai_with_retry(
        client=client,
        deployment_name=deployment_name,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_retries=3
    )


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
        # Build feedback list for prompt
        feedback_items = "\n".join([
            f"- {fb.get('recipe_name', 'Unknown')}: {fb.get('action', 'rated')} "
            f"(rating: {fb.get('rating', 'N/A')}, notes: {fb.get('notes', 'None')})"
            for fb in new_feedbacks
        ])
        
        previous_summary_text = "None (first time summarization)"
        if previous_summary:
            previous_summary_text = f"Embedding: {previous_summary.get('embedding_summary', 'N/A')}\nLLM: {previous_summary.get('llm_summary', 'N/A')}"
        
        likes_str = ', '.join(user_preferences.get('likedIngredients', []) or [])
        cuisines_str = ', '.join(user_preferences.get('favoriteCuisines', []) or [])
        activity = user_preferences.get('activityLevel', 'unknown')
        
        system_prompt = (
            "You are an expert nutritionist and chef analyzing user food preferences from feedback. "
            "Your task is to synthesize user feedback into two concise, distinct summaries: "
            "one optimized for vector embedding, one for LLM reasoning. "
            "Be precise. Capture preference evolution. Avoid redundancy."
        )
        
        user_prompt = f"""Analyze this user's evolving food preferences and create 2 summaries.

PREVIOUS SUMMARY (if any):
{previous_summary_text}

NEW FEEDBACK (5 recent interactions):
{feedback_items}

USER BACKGROUND:
- Likes: {likes_str if likes_str else 'Not specified'}
- Prefers: {cuisines_str if cuisines_str else 'Not specified'} cuisines
- Activity: {activity}

CRITICAL INSTRUCTIONS:
1. EMBEDDING_SUMMARY (max 2 sentences, ~100 chars):
   - Concise, keyword-focused for semantic vector search
   - Capture DISTINCT preferences (cuisines, ingredients, dietary goals)
   - Avoid overlap with LLM summary
   - Format: "User prefers [cuisines/ingredients]. They [dietary goal/activity]."

2. LLM_SUMMARY (3-5 sentences, ~300-400 chars):
   - Detailed reasoning for recipe recommendations
   - Include specific recipe TYPES or DISHES they liked/disliked
   - Reference dietary goals and health constraints
   - Mention preference EVOLUTION if evident from feedback
   - Personalized but not repetitive

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
            max_tokens=800,
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