from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, field_validator, EmailStr
from typing import Optional, Annotated, List
import json

from api.auth import get_current_active_user
from api.recipes import CONSIDERATION_SET_CACHE # Import the cache
from prisma.models import User
from database import db

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
    )

@router.patch("/profile", status_code=status.HTTP_200_OK)
async def update_user_profile(
    profile_data: UserProfileUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict:
    update_dict = profile_data.model_dump(exclude_unset=True)

    if "likedIngredients" in update_dict or "dislikedIngredients" in update_dict:
        update_dict["onboardingCompleted"] = True

    if "dietaryProfile" in update_dict and update_dict["dietaryProfile"] is not None:
        update_dict["dietaryProfile"] = json.dumps(update_dict["dietaryProfile"])

    await db.user.update(
        where={"id": current_user.id},
        data=update_dict,
    )

    # --- Cache Invalidation ---
    if current_user.id in CONSIDERATION_SET_CACHE:
        print(f"Invalidating cache for user {current_user.id}")
        del CONSIDERATION_SET_CACHE[current_user.id]
    # --- End Cache Invalidation ---
    
    return {"status": "success", "message": "Profile updated and recommendation cache cleared."}
