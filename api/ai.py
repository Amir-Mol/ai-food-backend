from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Annotated

from api.auth import get_current_active_user
from prisma.models import User

router = APIRouter(
    prefix="/ai",
    tags=["ai"],
)


class IngredientList(BaseModel):
    """Model for a list of ingredients."""
    ingredients: List[str]

class IngredientInsightsResponse(BaseModel):
    """Model for the AI-driven insights response."""
    recipe_ideas: List[str]

def generate_insights_from_ingredients(ingredients: List[str]) -> List[str]:
    """
    Mock AI function to generate recipe ideas from a list of ingredients.
    """
    # In a real application, this would use an LLM or a recipe database.
    if not ingredients:
        return ["Try adding some ingredients to get recipe ideas!"]

    first_ingredient = ingredients[0].title()
    return [
        f"{first_ingredient} and Avocado Toast",
        f"Spicy {first_ingredient} Stir-fry",
        f"Simple {first_ingredient} and Pasta Salad",
    ]

@router.post("/ingredient-insights", response_model=IngredientInsightsResponse)
async def get_ingredient_insights(
    data: IngredientList,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> IngredientInsightsResponse:
    """Receives a list of ingredients and returns AI-driven recipe ideas."""
    recipe_ideas = generate_insights_from_ingredients(data.ingredients)
    return IngredientInsightsResponse(recipe_ideas=recipe_ideas)