from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, field_validator, EmailStr
from typing import Optional, Annotated, List
import json
import asyncio

from api.auth import get_current_active_user
from prisma.models import User
from database import db
from tasks.recommendation_generator import trigger_recommendation_generation_on_onboarding

router = APIRouter(
    prefix="/user",
    tags=["user"],
)


class DietaryItem(BaseModel):
    selected: List[str]
    other: str


class DietaryProfileData(BaseModel):
    dietaryRestrictions: DietaryItem
    foodAllergies: DietaryItem
    healthConditions: DietaryItem


class UserProfileResponse(BaseModel):
    name: Optional[str] = None
    email: EmailStr
    age: Optional[int] = None
    gender: Optional[str] = None
    height: Optional[float] = None
    heightUnit: Optional[str] = None
    weight: Optional[float] = None
    weightUnit: Optional[str] = None
    activityLevel: Optional[str] = None
    dietaryProfile: Optional[DietaryProfileData] = None
    likedIngredients: Optional[List[str]] = None
    dislikedIngredients: Optional[List[str]] = None
    favoriteCuisines: Optional[List[str]] = None
    otherCuisine: Optional[str] = None
    total_feedbacks_submitted: int = 0
    isExperimentComplete: bool = False
    totalRecommendationsGenerated: int = 0
    currentCycleNumber: int = 0
    group: str = "transparency"
    surveyComplete: bool = False

class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    height: Optional[float] = None
    heightUnit: Optional[str] = None
    weight: Optional[float] = None
    weightUnit: Optional[str] = None
    activityLevel: Optional[str] = None
    dietaryProfile: Optional[DietaryProfileData] = None
    likedIngredients: Optional[List[str]] = None
    dislikedIngredients: Optional[List[str]] = None
    favoriteCuisines: Optional[List[str]] = None
    otherCuisine: Optional[str] = None

    @field_validator('likedIngredients', 'dislikedIngredients', mode='before')
    @classmethod
    def split_string(cls, v: object) -> Optional[List[str]]:
        if isinstance(v, str):
            return [item.strip() for item in v.split(',') if item.strip()]
        return v


@router.get("/profile", response_model=UserProfileResponse)
async def get_user_profile(current_user: Annotated[User, Depends(get_current_active_user)]):
    # Count total feedbacks submitted by the user (only records with actual feedback, not just logged recommendations)
    total_feedbacks = await db.trainingrecord.count(where={"userId": current_user.id, "liked": {"not": None}})
    
    return UserProfileResponse(
        name=current_user.name,
        email=current_user.email,
        age=current_user.age,
        gender=current_user.gender,
        height=current_user.height,
        heightUnit=current_user.heightUnit,
        weight=current_user.weight,
        weightUnit=current_user.weightUnit,
        activityLevel=current_user.activityLevel,
        dietaryProfile=current_user.dietaryProfile,
        likedIngredients=current_user.likedIngredients,
        dislikedIngredients=current_user.dislikedIngredients,
        favoriteCuisines=current_user.favoriteCuisines,
        otherCuisine=current_user.otherCuisine,
        total_feedbacks_submitted=total_feedbacks,
        isExperimentComplete=current_user.isExperimentComplete or False,
        totalRecommendationsGenerated=current_user.totalRecommendationsGenerated or 0,
        currentCycleNumber=current_user.currentCycleNumber or 0,
        group=current_user.group or "transparency",
        surveyComplete=current_user.surveyComplete or False,
    )

@router.patch("/profile", status_code=status.HTTP_200_OK)
async def update_user_profile(
    profile_data: UserProfileUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict:
    update_dict = profile_data.model_dump(exclude_unset=True)

    if "dietaryProfile" in update_dict and update_dict["dietaryProfile"] is not None:
        update_dict["dietaryProfile"] = json.dumps(update_dict["dietaryProfile"])

    await db.user.update(
        where={"id": current_user.id},
        data=update_dict,
    )
    
    return {"status": "success", "message": "Profile updated successfully."}


@router.post("/complete-onboarding", status_code=status.HTTP_200_OK)
async def complete_onboarding(current_user: Annotated[User, Depends(get_current_active_user)]):
    """
    Called by frontend after final onboarding screen (after consent checkbox).
    Marks onboarding as complete and triggers auto-generation of initial recommendations (asynchronously).
    
    Response:
    {
        "status": "success",
        "message": "Onboarding completed. Recommendations generation started."
    }
    
    Frontend behavior:
    - Navigates to TutorialScreen (no polling needed)
    - User manually goes to HomeScreen after tutorial
    - HomeScreen starts polling to wait for recommendations to be ready
    """
    # Mark onboarding as complete
    await db.user.update(
        where={"id": current_user.id},
        data={"onboardingCompleted": True}
    )
    
    # Trigger async generation (fire-and-forget)
    asyncio.create_task(
        trigger_recommendation_generation_on_onboarding(current_user.id)
    )
    
    return {
        "status": "success",
        "message": "Onboarding completed. Recommendations generation started."
    }
