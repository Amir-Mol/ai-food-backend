from typing import List, Optional

from pydantic import BaseModel


class DietaryItem(BaseModel):
    """Represents a dietary item with a list of selected options and an 'other' text field."""

    selected: List[str]
    other: str


class DietaryProfileData(BaseModel):
    """Represents the structured dietary profile of a user."""

    dietaryRestrictions: Optional[DietaryItem] = None
    foodAllergies: Optional[DietaryItem] = None
    healthConditions: Optional[DietaryItem] = None


class AIUserProfile(BaseModel):
    """Represents the user profile data used for AI processing."""

    age: Optional[int] = None
    gender: Optional[str] = None
    height: Optional[float] = None
    weight: Optional[float] = None
    activityLevel: Optional[str] = None
    dietaryProfile: Optional[DietaryProfileData] = None
    likedIngredients: Optional[List[str]] = None
    dislikedIngredients: Optional[List[str]] = None
    favoriteCuisines: Optional[List[str]] = None
