import os
import logging
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

async def get_recipe_suggestion(user_profile: AIUserProfile, recipe_candidates: list):
    """
    Generates recipe suggestions using the Microsoft Azure OpenAI Service.
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
        "- Output ONLY a valid JSON object following the schema."
    )

    # User prompt: inputs + JSON schema
    user_prompt = f"""
    Here is the user's profile:
    ---USER PROFILE---
    {user_profile_str}
    ------------------

    Here is the list of recipe candidates:
    ---RECIPE CANDIDATES---
    {recipe_candidates_str}
    -----------------------

    Now return the final ranked recommendations in this exact structure:

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
    # In Azure, the "model" parameter is actually your "Deployment Name"
    deployment_name = os.getenv("AZURE_DEPLOYMENT_NAME", "gpt-4o-deployment")

    try:
        response = await client.chat.completions.create(
            model=deployment_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=1500,
            response_format={"type": "json_object"}
        )
        suggestion = response.choices[0].message.content
        return suggestion.strip() if suggestion else ERROR_MESSAGE
    except APIError as e:
        logger.error(f"Azure OpenAI API error: {e}")
        return ERROR_MESSAGE
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return ERROR_MESSAGE