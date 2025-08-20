from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, Annotated, List, Dict

from api.auth import get_current_active_user
from prisma.models import User
from database import db

router = APIRouter(
    prefix="/recommendations",
    tags=["recommendations"],
)


class MealRecommendation(BaseModel):
    id: str
    name: str
    imageUrl: str
    fsaHealthScore: int = Field(..., ge=4, le=12)

class NutritionalInfo(BaseModel):
    """Detailed nutritional information for a meal."""
    calories: str
    protein: str
    carbs: str
    fat: str

class MealRecommendationDetail(MealRecommendation):
    """Extends MealRecommendation with full details for the meal screen."""
    description: str
    nutritionalInfo: NutritionalInfo
    ingredients: List[str]
    recipeUrl: str
    aiExplanation: str


class RecommendationsResponse(BaseModel):
    status: str
    showTransparencyFeatures: bool
    recommendations: List[MealRecommendation]

class FeedbackCreate(BaseModel):
    """Model for creating feedback on a meal recommendation."""
    liked: bool
    healthinessScore: int = Field(..., ge=1, le=5)
    tastinessScore: int = Field(..., ge=1, le=5)
    intentToTryScore: int = Field(..., ge=1, le=5)

# A mock database of all meals. In a real application, this would be a database table.
MOCK_MEALS_DB = [
    {
        "id": "meal_001", "name": "Grilled Chicken Salad", "imageUrl": "https://images.unsplash.com/photo-1551248429-4097c682f62c", "fsaHealthScore": 9
    },
    {
        "id": "meal_002", "name": "Quinoa Bowl with Roasted Vegetables", "imageUrl": "https://images.unsplash.com/photo-1512621776951-a57141f2eefd", "fsaHealthScore": 11
    },
    {
        "id": "meal_003", "name": "Lentil Soup", "imageUrl": "https://images.unsplash.com/photo-1608797178823-dec1638c560a", "fsaHealthScore": 7
    },
    {
        "id": "meal_004", "name": "Apple Slices with Peanut Butter", "imageUrl": "https://images.unsplash.com/photo-1558985250-27a416a95336", "fsaHealthScore": 8
    },
    {
        "id": "meal_005", "name": "Greek Yogurt with Berries", "imageUrl": "https://images.unsplash.com/photo-1587435323762-62c6351a4d78", "fsaHealthScore": 10
    },
]


def get_ai_recommendations(user: User, mealType: Optional[str] = None) -> RecommendationsResponse:
    """
    Mock AI engine to generate meal recommendations.
    In a real application, this would involve a call to a machine learning model.
    """
    if mealType and "snack" in mealType.lower():
        recs = [
            meal for meal in MOCK_MEALS_DB if meal["id"] in ["meal_004", "meal_005"]
        ]
    else:
        recs = [
            meal for meal in MOCK_MEALS_DB if meal["id"] in ["meal_001", "meal_002", "meal_003"]
        ]

    return RecommendationsResponse(
        status="success",
        showTransparencyFeatures=True,
        recommendations=recs,
    )

@router.get("/", response_model=RecommendationsResponse)
async def get_recommendations(
    current_user: Annotated[User, Depends(get_current_active_user)],
    mealType: Optional[str] = None,
) -> RecommendationsResponse:
    """Returns recommendations based on user profile."""
    return get_ai_recommendations(user=current_user, mealType=mealType)

@router.get("/{id}", response_model=MealRecommendationDetail)
async def get_recommendation_detail(id: str):
    """
    Returns detailed information for a specific meal recommendation.
    """
    meal = next((m for m in MOCK_MEALS_DB if m["id"] == id), None)

    if not meal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Meal not found"
        )

    detailed_meal_data = meal.copy()
    detailed_meal_data.update({
        "description": "A delicious and healthy meal option, perfect for any time of the day. Packed with nutrients to keep you energized.",
        "nutritionalInfo": {
            "calories": "450 kcal",
            "protein": "30g",
            "carbs": "20g",
            "fat": "25g"
        },
        "ingredients": ["Main Ingredient 1", "Vegetable/Fruit 1", "Healthy Fat Source", "Seasoning/Spice 1", "Dressing/Sauce"],
        "recipeUrl": "https://example.com/recipe/" + meal["id"],
        "aiExplanation": "This meal was recommended because it aligns with your preference for high-protein, low-carb meals and does not contain any of your disliked ingredients. Its high health score indicates a balanced nutritional profile."
    })

    return detailed_meal_data


@router.post("/{recommendation_id}/feedback")
async def submit_feedback(
    recommendation_id: str,
    feedback: FeedbackCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Dict[str, str]:
    """
    Submits feedback for a recommendation and updates the corresponding training record.
    """
    # Find the most recent training record for this user and recommendation
    training_record = await db.trainingrecord.find_first(
        where={
            "userId": current_user.id,
            "recommendationId": recommendation_id,
        },
        order={"createdAt": "desc"},
    )

    if not training_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No training record found for user {current_user.id} and recommendation {recommendation_id}"
        )

    # Update the found record with the new feedback
    await db.trainingrecord.update(
        where={"id": training_record.id},
        data={
            "liked": feedback.liked,
            "healthinessScore": feedback.healthinessScore,
            "tastinessScore": feedback.tastinessScore,
            "intentToTryScore": feedback.intentToTryScore,
        },
    )

    return {"status": "success", "message": "Feedback received successfully."}