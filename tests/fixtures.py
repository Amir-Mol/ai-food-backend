"""
Test fixtures and data helpers for Phase 5 testing.
Provides reusable test users, feedback data, and authentication tokens.
"""

import json
from datetime import datetime
from database import db
from prisma.models import User as PrismaUser


# Test user profiles used across all scenarios
TEST_USER_PROFILES = {
    "user_a": {
        "email": "test_user_a@example.com",
        "name": "Test User A",
        "age": 30,
        "gender": "male",
        "height": 180,
        "weight": 75,
        "activityLevel": "moderately active",
        "likedIngredients": ["garlic", "tomato", "olive oil"],
        "dislikedIngredients": ["mushroom"],
        "favoriteCuisines": ["Italian", "Mediterranean"],
        "group": "treatment"
    },
    "user_b": {
        "email": "test_user_b@example.com",
        "name": "Test User B",
        "age": 28,
        "gender": "female",
        "height": 165,
        "weight": 60,
        "activityLevel": "active",
        "likedIngredients": ["chicken", "rice", "broccoli"],
        "dislikedIngredients": ["beef"],
        "favoriteCuisines": ["Asian", "Mediterranean"],
        "dietaryProfile": {"vegetarian": False},
        "group": "control"
    }
}


async def create_test_user(
    profile_key: str = "user_a",
    email: str = None,
    group: str = None
) -> PrismaUser:
    """
    Create a test user in the database.
    
    Args:
        profile_key: Key from TEST_USER_PROFILES
        email: Override email (for dynamic user creation)
        group: Override group ('treatment' or 'control')
    
    Returns:
        Created User object
    """
    profile = TEST_USER_PROFILES.get(profile_key, TEST_USER_PROFILES["user_a"]).copy()
    
    # Override email if provided
    if email:
        profile["email"] = email
    
    # Override group if provided
    if group:
        profile["group"] = group
    
    # Check if user already exists
    existing = await db.user.find_unique(where={"email": profile["email"]})
    if existing:
        print(f"[Fixture] User {profile['email']} already exists")
        return existing
    
    # Create new user
    user = await db.user.create(
        data={
            "email": profile["email"],
            "name": profile["name"],
            "age": profile["age"],
            "gender": profile["gender"],
            "height": profile["height"],
            "weight": profile["weight"],
            "activityLevel": profile["activityLevel"],
            "likedIngredients": profile["likedIngredients"],
            "dislikedIngredients": profile["dislikedIngredients"],
            "favoriteCuisines": profile["favoriteCuisines"],
            "group": profile["group"],
            "recommendationGenerationStatus": "idle",
        }
    )
    
    print(f"[Fixture] Created test user: {user.email} (ID: {user.id})")
    return user


async def get_test_user(email: str) -> PrismaUser:
    """Get a test user by email"""
    user = await db.user.find_unique(where={"email": email})
    if not user:
        raise ValueError(f"User not found: {email}")
    return user


# Test feedback data
SAMPLE_FEEDBACKS = [
    {
        "recipe_name": "Spaghetti Carbonara",
        "action": "liked",
        "rating": 5,
        "notes": "Delicious and authentic"
    },
    {
        "recipe_name": "Grilled Chicken Salad",
        "action": "liked",
        "rating": 4,
        "notes": "Healthy and tasty"
    },
    {
        "recipe_name": "Vegetable Stir Fry",
        "action": "liked",
        "rating": 5,
        "notes": "Great flavor, easy to prepare"
    },
    {
        "recipe_name": "Mushroom Risotto",
        "action": "disliked",
        "rating": 2,
        "notes": "Too many mushrooms"
    },
    {
        "recipe_name": "Peanut Noodles",
        "action": "disliked",
        "rating": 1,
        "notes": "Peanut allergy concern"
    }
]


def get_sample_feedback(count: int = 5) -> list:
    """
    Get sample feedback items.
    
    Args:
        count: Number of feedback items to return
    
    Returns:
        List of feedback dictionaries
    """
    return SAMPLE_FEEDBACKS[:count]


def generate_test_token(user_id: str) -> str:
    """
    Generate a mock bearer token for testing.
    Format: Bearer test_{user_id}_{timestamp}
    
    Real auth would verify JWT, but for tests we mock the auth dependency.
    """
    from datetime import datetime
    timestamp = int(datetime.utcnow().timestamp())
    return f"test_{user_id}_{timestamp}"


def print_user_state(user: PrismaUser):
    """Pretty-print user state for debugging"""
    print(f"""
    ====================================================
                 USER STATE SNAPSHOT                    
    ====================================================
    ID: {user.id}
    Email: {user.email}
    Status: {user.recommendationGenerationStatus}
    Recommendations Ready At: {user.recommendationsReadyAt}
    Next Allowed Gen At: {user.nextAllowedGenerationAt}
    Feedback Summary (Embedding): {user.feedbackSummaryForEmbedding[:50] if user.feedbackSummaryForEmbedding else 'None'}...
    Feedback Summary (LLM): {user.feedbackSummaryForLLM[:50] if user.feedbackSummaryForLLM else 'None'}...
    Feedback Summary Updated: {user.feedbackSummaryLastUpdatedAt}
    Recommendations Count: {len(user.recommendations) if user.recommendations else 0}
    ====================================================
    """)
