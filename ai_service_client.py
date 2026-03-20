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