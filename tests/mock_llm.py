"""
Mock Azure OpenAI client for testing.
Returns deterministic responses without calling the real API.
"""

import json
from typing import Optional
from unittest.mock import AsyncMock, patch
from models.ai_profile import AIUserProfile


class MockAzureOpenAI:
    """Mock Azure OpenAI that returns deterministic recommendations"""
    
    def __init__(self):
        self.call_count = 0
        self.last_user_profile = None
        self.last_recipe_candidates = None
    
    async def chat_completions_create(
        self,
        model: str,
        messages: list,
        temperature: float,
        max_tokens: int,
        response_format: dict = None
    ) -> dict:
        """Mock response for recipe suggestions"""
        self.call_count += 1
        
        # Extract user profile and candidates from messages
        user_msg = messages[1]["content"]
        
        # Parse the user prompt to extract recipe IDs
        # The candidates are in JSON format in the prompt
        try:
            candidates_start = user_msg.find("---RECIPE CANDIDATES---") + len("---RECIPE CANDIDATES---")
            candidates_end = user_msg.find("-----------------------")
            candidates_json = user_msg[candidates_start:candidates_end].strip()
            candidates = json.loads(candidates_json)
        except:
            # Fallback: use first 5 if parsing fails
            candidates = []
        
        # Create deterministic recommendations from first 5 candidates
        recommendations = []
        for i, recipe in enumerate(candidates[:5]):
            recommendations.append({
                "recipeId": str(recipe.get("recipeId", f"recipe_{i}")),
                "name": recipe.get("name", f"Recipe {i+1}"),
                "explanation": (
                    f"This is a perfectly suited recipe for your dietary preferences. "
                    f"It contains ingredients you love and aligns with your health goals. "
                    f"The nutritional profile is excellent, providing balanced macronutrients. "
                    f"This recipe scored high on our ranking for your specific profile. "
                    f"We recommend trying it next time you're planning a meal."
                )
            })
        
        response_data = {
            "ranked_recommendations": recommendations
        }
        
        # Create mock response object
        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock()]
        mock_response.choices[0].message = AsyncMock()
        mock_response.choices[0].message.content = json.dumps(response_data)
        
        return mock_response


def mock_get_azure_openai_client():
    """Returns mock Azure OpenAI client"""
    return MockAzureOpenAI()


async def mock_get_recipe_suggestion(
    user_profile: AIUserProfile,
    recipe_candidates: list
) -> str:
    """
    Mock implementation of get_recipe_suggestion.
    Returns deterministic JSON response without calling Azure OpenAI.
    """
    # Create deterministic recommendations from first 5 candidates
    recommendations = []
    for i, recipe in enumerate(recipe_candidates[:5]):
        recommendations.append({
            "recipeId": str(recipe.get("recipeId", f"recipe_{i}")),
            "name": recipe.get("name", f"Recipe {i+1}"),
            "explanation": (
                f"This recipe perfectly matches your taste profile and dietary goals. "
                f"It incorporates ingredients you enjoy while maintaining nutritional balance. "
                f"The preparation method is straightforward and healthy. "
                f"Based on your preference history, this scored highly in our ranking. "
                f"We highly recommend this for your next meal."
            )
        })
    
    response_data = {
        "ranked_recommendations": recommendations
    }
    
    return json.dumps(response_data)


async def mock_summarize_feedback_history(
    previous_summary: Optional[dict],
    new_feedbacks: list,
    user_preferences: dict
) -> dict:
    """
    Mock implementation of summarize_feedback_history.
    Returns deterministic summaries without calling Azure OpenAI.
    """
    # Count liked vs disliked
    liked_count = sum(1 for fb in new_feedbacks if fb.get("action") == "liked")
    disliked_count = len(new_feedbacks) - liked_count
    
    # Create deterministic summaries
    embedding_summary = (
        f"User prefers recipes with healthy, fresh ingredients and moderate portion sizes. "
        f"They have shown interest in Mediterranean and Asian cuisines based on recent feedback."
    )
    
    llm_summary = (
        f"Based on recent interactions, the user is developing a preference for plant-based meals "
        f"and Mediterranean cuisine. They have rated {liked_count} recipes highly and {disliked_count} recipes lower. "
        f"They show consistent interest in recipes with fresh vegetables and lean proteins. "
        f"The user appears health-conscious and willing to explore diverse cuisines. "
        f"Future recommendations should emphasize Mediterranean and Asian plant-forward dishes."
    )
    
    return {
        "embedding_summary": embedding_summary,
        "llm_summary": llm_summary,
        "feedback_count": len(new_feedbacks)
    }


def create_mock_patches():
    """
    Creates patches for the async Azure OpenAI calls.
    Returns list of patch objects to be used as fixtures.
    """
    patches = [
        patch(
            "ai_service_client.get_recipe_suggestion",
            side_effect=mock_get_recipe_suggestion
        ),
        patch(
            "ai_service_client.summarize_feedback_history",
            side_effect=mock_summarize_feedback_history
        )
    ]
    return patches
