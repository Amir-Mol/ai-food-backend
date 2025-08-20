import os
import logging
from functools import lru_cache
from openai import AsyncOpenAI, APIError
import json

from models.ai_profile import AIUserProfile

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ERROR_MESSAGE = "Sorry, I couldn't generate a recipe at this time. Please try again later."

@lru_cache
def get_openai_client() -> AsyncOpenAI:
    """
    Initializes and returns a singleton AsyncOpenAI client.
    It's wrapped in a function to ensure OPENAI_API_KEY is loaded
    from the environment before the client is created.
    """
    # The client is initialized here, when the function is first called.
    # By this time, main.py will have already called load_dotenv().
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # This provides a clearer, immediate error if the key is missing.
        logger.critical("The OPENAI_API_KEY environment variable is not set.")
        # The OpenAIError will still be raised by the client, but this log helps pinpoint the issue.

    return AsyncOpenAI(api_key=api_key)


async def get_recipe_suggestion(user_profile: AIUserProfile, recipe_candidates: list):
    """
    Generates a recipe suggestion using the OpenAI API with a detailed prompt and a JSON structure example.
    """
    # Convert the user profile and candidates to a string format for the prompt
    user_profile_str = "\n".join([f"{key}: {value}" for key, value in user_profile.model_dump().items() if value])
    recipe_candidates_str = json.dumps(recipe_candidates, indent=2)

    system_prompt = (
        "You are an expert nutritionist and chef. Your task is to analyze a user's profile and a list of "
        "recipe candidates. Re-rank the candidates and select the top 5 that best fit the user's needs. "
        "For each of the top 5, you must provide a balanced and honest explanation paragraph."
        "IMPORTANT: Address the user directly in the second person, using 'you' and 'your'."
    )

    user_prompt = f"""
    Here is the user's profile:
    ---USER PROFILE---
    {user_profile_str}
    ------------------

    Here is the list of recipe candidates:
    ---RECIPE CANDIDATES---
    {recipe_candidates_str}
    -----------------------

    Perform the following tasks:
    1. Re-rank the list and select the top 5 best options for this user (**Important:** The number
    of recipes you return must not be more than the number of candidates provided. Do not invent new recipes.).
    2. For each of the top 5, provide a 'pros' list and a 'cons' list based on the user's profile.
    3. **Crucially, you must include the original 'recipeId' for each recipe from the candidate list in your response.**

    1. Re-rank the provided recipe candidates and select up to 5 of the best options for this user.
       **Important:** The number of recipes you return must not be more than the number of candidates provided. Do not invent new recipes.
    2. For each of the top 5, write a concise and helpful explanation of about 4-5 sentences. The explanation paragraph must be balanced:
       - Start with why it matches the user's tastes and preferences.
       - Then, discuss its health aspects in the context of the user's profile.
       - Finally, mention any potential drawbacks or considerations.
    3. **Crucially, you must include the original 'recipeId' for each recipe from the candidate list in your response.**
    
    
    IMPORTANT: Your final output MUST be a single, valid JSON object. Do not include any text or markdown formatting before or after the JSON.
    The JSON object must follow this exact structure:

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

    client = get_openai_client()
    ai_model = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

    try:
        response = await client.chat.completions.create(
            model=ai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=1500  # Increased max_tokens for a more detailed response
        )
        suggestion = response.choices[0].message.content
        return suggestion.strip() if suggestion else ERROR_MESSAGE
    except APIError as e:
        logger.error(f"An OpenAI API error occurred: {e}")
        return ERROR_MESSAGE
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        return ERROR_MESSAGE