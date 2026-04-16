"""
Personalized recipe recommendation engine using precomputed embeddings.

Loads pre-generated recipe embeddings and uses a SentenceTransformer model to 
embed a user's profile into the same vector space. It then scores recipes based 
on cosine similarity to the user profile and applies filtering rules (dietary 
restrictions, allergies, disliked ingredients, health conditions) as well as 
bonus factors (likes, cuisines, ratings). Returns a ranked list of recipes 
forming a "consideration set" for the user.
"""

import ast
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from config import CONSIDERATION_SET_SIZE

# It is assumed that the model is loaded once when the application starts.
embedding_model = SentenceTransformer('thenlper/gte-small')

def _create_user_document(
    user_profile: Dict[str, Any],
    feedback_summary: Optional[str] = None,
    liked_recipe_names: Optional[List[str]] = None,
    disliked_recipe_names: Optional[List[str]] = None
) -> str:
    """Creates a single text string from a user's profile for embedding."""
    likes = ', '.join(user_profile.get('likedIngredients', []))
    dislikes = ', '.join(user_profile.get('dislikedIngredients', []))
    cuisines = ', '.join(user_profile.get('favoriteCuisines', []))
    
    # Safely access nested dietary restrictions, handling missing keys or None values.
    dietary_profile = user_profile.get('dietaryProfile') or {}
    dietary_restrictions = dietary_profile.get('dietaryRestrictions') or {}
    diet_info = ', '.join(dietary_restrictions.get('selected', []))

    document = (
        f"A user who likes {likes}. "
        + (f"They dislike {dislikes}. " if dislikes else "")
        + f"They enjoy {cuisines} cuisines. "
        f"Their dietary profile includes: {diet_info}. "
        f"They have an activity level of {user_profile.get('activityLevel', 'unknown')}."
    )
    
    # Add directly observed liked recipes for stronger embedding signal
    if liked_recipe_names:
        liked_str = ', '.join(liked_recipe_names[:20])  # cap to avoid runaway document length
        document += f" They have previously liked: {liked_str}."
    
    # Add directly observed disliked recipes to push embedding away from those
    if disliked_recipe_names:
        disliked_str = ', '.join(disliked_recipe_names[:20])  # cap to avoid runaway document length
        document += f" They have previously disliked: {disliked_str}."
    
    # Add feedback summary if available (evolved preferences)
    if feedback_summary:
        document += f" Recent preferences: {feedback_summary}"
    
    return document

def _estimate_per_meal_calorie_target(user_profile: Dict[str, Any]) -> Optional[float]:
    """
    Estimates a user's per-meal calorie needs based on their profile using the
    Mifflin-St Jeor equation for BMR and TDEE.
    """
    # Required fields from the user profile
    weight_kg = user_profile.get('weight')
    height_cm = user_profile.get('height')
    age = user_profile.get('age')
    # Safely get and lowercase gender and activity level, defaulting to '' if missing or None.
    gender = (user_profile.get('gender') or '').lower()
    activity_level = (user_profile.get('activityLevel') or '').lower()

    if not all([weight_kg, height_cm, age, gender, activity_level]):
        return None # Not enough data to make a calculation

    # 1. Calculate Basal Metabolic Rate (BMR) using Mifflin-St Jeor
    if gender == 'male':
        bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) + 5
    elif gender == 'female':
        bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) - 161
    else:
        return None # Gender must be 'male' or 'female'

    # 2. Define activity multipliers for Total Daily Energy Expenditure (TDEE)
    activity_multipliers = {
        'sedentary': 1.2,
        'lightly active': 1.375,
        'moderately active': 1.55,
        'very active': 1.725,
        'extra active': 1.9
    }
    multiplier = activity_multipliers.get(activity_level.replace(" ", "_"), 1.2)
    
    tdee = bmr * multiplier

    # 3. Assume 3 main meals per day to get a per-meal target
    per_meal_target = tdee / 3
    
    return per_meal_target


def _calculate_score(
    user_profile: Dict[str, Any],
    recipe: pd.Series,
    user_embedding: np.ndarray,
    recipe_embedding: np.ndarray
) -> float:
    
    """
    Calculates a preference score.
    """
    embedding_sim = cosine_similarity(user_embedding, recipe_embedding)[0][0]

    # --- Hard Constraints ---
    # Safely access nested profile data, defaulting to empty structures if keys are missing or values are None.
    dietary_profile = user_profile.get('dietaryProfile') or {}
    food_allergies_profile = dietary_profile.get('foodAllergies') or {}

    # Allergy Check: Safely get list of allergies.
    # Map high-level allergen categories to common ingredient substrings.
    ALLERGEN_MAP = {
        "shellfish": ["shrimp", "prawn", "crab", "lobster", "crayfish", "scallop", "clam", "oyster", "mussel", "squid", "octopus"],
        "tree nuts": ["almond", "cashew", "walnut", "pecan", "pistachio", "hazelnut", "macadamia", "brazil nut", "pine nut"],
        "peanuts": ["peanut", "groundnut"],
        "dairy": ["milk", "cheese", "butter", "cream", "yogurt", "lactose", "whey", "casein"],
        "gluten": ["wheat", "flour", "bread", "barley", "rye", "spelt"],
        "eggs": ["egg", "eggs"],
        "soy": ["soy", "tofu", "tempeh", "edamame", "miso"],
        "fish": ["salmon", "tuna", "cod", "tilapia", "halibut", "anchovy", "sardine", "herring", "mackerel"],
        "sesame": ["sesame", "tahini"],
    }
    user_allergies_raw = [a.lower() for a in food_allergies_profile.get('selected', [])]
    # Build the full set of ingredient substrings to block
    allergen_terms = set()
    for raw in user_allergies_raw:
        mapped = ALLERGEN_MAP.get(raw)
        if mapped:
            allergen_terms.update(mapped)
        else:
            allergen_terms.add(raw)  # fall back to exact term
    allergy_ingredients = [str(ing).lower() for ing in (recipe['ingredients_title'] if recipe['ingredients_title'] is not None else [])]
    if allergen_terms and any(term in ing for term in allergen_terms for ing in allergy_ingredients):
        return 0.0

    # Dietary Doctrine Check: Safely get list of dietary restrictions.
    dietary_restrictions = dietary_profile.get('dietaryRestrictions') or {}
    user_diet = set(dietary_restrictions.get('selected', []))
    recipe_tags = set(recipe['tags'])
    if 'Vegan' in user_diet and 'Vegan' not in recipe_tags:
        return 0.0
    if 'Vegetarian' in user_diet and 'Vegetarian' not in recipe_tags:
        return 0.0
    if 'No Pork' in user_diet and 'Contains Pork' in recipe_tags:
        return 0.0
    
    # --- Soft Constraints & Scoring ---
    # The score is now primarily driven by semantic similarity.
    score = embedding_sim

    # Dislikes Penalty (uses 'ingredients_title')
    # Use substring match within each ingredient string to catch plurals/partial names.
    user_dislikes = set(dislike.lower() for dislike in user_profile.get('dislikedIngredients', []))
    recipe_ingredients = [str(ing).lower() for ing in (recipe['ingredients_title'] if recipe['ingredients_title'] is not None else [])]
    if user_dislikes and any(dislike in ing for dislike in user_dislikes for ing in recipe_ingredients):
        score *= 0.3 # Apply significant penalty

    # Custom Forbidden Ingredients Penalty (from the 'other' field) - now a soft constraint
    other_restrictions_str = dietary_restrictions.get('other')
    if other_restrictions_str:
        forbidden_ingredients = {item.strip().lower() for item in other_restrictions_str.split(',')}
        if any(forbidden in ing for forbidden in forbidden_ingredients for ing in recipe_ingredients):
            score *= 0.3 # Apply same penalty as regular dislikes

    # Health Goal Penalty: Safely get list of health conditions.
    health_conditions_profile = dietary_profile.get('healthConditions') or {}
    health_conditions = health_conditions_profile.get('selected', [])
    if 'Diabetes' in health_conditions and recipe['sugars_per_serving [g]'] > 15:
        score *= 0.5
    if 'High Blood Pressure' in health_conditions and recipe['sodium_per_serving [mg]'] > 500:
        score *= 0.6

    # Likes Bonus (uses 'ingredients_title')
    user_likes = set(like.lower() for like in user_profile.get('likedIngredients', []))
    if user_likes and any(like in recipe['ingredients_title'] for like in user_likes):
        score *= 1.2 # Apply small bonus
                
    return score

def _format_output(top_recipes_df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Formats the final DataFrame into the required list of dicts comprehensive list of 15 fields.
    """
    output_keys = {
        'recipeId': 'recipe_id', 
        'name': 'title',
        'recipeUrl': 'recipe_url',
        'imageUrl': 'image_url',
        'ingredients': 'ingredients_title',
        'tags': 'tags',
        'healthScore': 'health_score',
        # Per-serving fields (kept for backward compatibility)
        'calories_per_serving [cal]': 'calories_per_serving [cal]',
        'totalfat_per_serving [g]': 'totalfat_per_serving [g]',
        'saturatedfat_per_serving [g]': 'saturatedfat_per_serving [g]',
        'cholesterol_per_serving [mg]': 'cholesterol_per_serving [mg]',
        'sodium_per_serving [mg]': 'sodium_per_serving [mg]',
        'totalcarbohydrate_per_serving [g]': 'totalcarbohydrate_per_serving [g]',
        'sugars_per_serving [g]': 'sugars_per_serving [g]',
        'protein_per_serving [g]': 'protein_per_serving [g]',
        # Per-100g fields (for API response)
        'calories_per_100g [cal]': 'calories_per_100g [cal]',
        'totalfat_per_100g [g]': 'totalfat_per_100g [g]',
        'saturatedfat_per_100g [g]': 'saturatedfat_per_100g [g]',
        'cholesterol_per_100g [mg]': 'cholesterol_per_100g [mg]',
        'sodium_per_100g [mg]': 'sodium_per_100g [mg]',
        'totalcarbohydrate_per_100g [g]': 'totalcarbohydrate_per_100g [g]',
        'sugars_per_100g [g]': 'sugars_per_100g [g]',
        'protein_per_100g [g]': 'protein_per_100g [g]'
    }
    
    output_list = []
    for _, recipe in top_recipes_df.iterrows():
        recipe_dict = {
            out_key: recipe.get(in_key, None) for out_key, in_key in output_keys.items()
        }

        # Ensure list-like fields are actual Python lists to prevent Pydantic errors
        # with NumPy arrays during serialization.
        ingredients = recipe_dict.get('ingredients')
        if ingredients is not None:
            recipe_dict['ingredients'] = list(ingredients)

        tags = recipe_dict.get('tags')
        if tags is not None:
            if isinstance(tags, str):
                try:
                    recipe_dict['tags'] = ast.literal_eval(tags)
                except (ValueError, SyntaxError):
                    recipe_dict['tags'] = [tags]
            else:
                recipe_dict['tags'] = list(tags)

        output_list.append(recipe_dict)
        
    return output_list

def generate_consideration_set(
    user_profile: Dict[str, Any],
    recipes_df: pd.DataFrame,
    recipe_embeddings: np.ndarray,
    consideration_set_size: int = CONSIDERATION_SET_SIZE,
    feedback_summary: Optional[str] = None,
    seen_recipe_ids: Optional[set] = None,
    liked_recipe_names: Optional[List[str]] = None,
    disliked_recipe_names: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    The main function for the Stage 1 Filtering Engine.
    Orchestrates the process of generating a personalized 'Consideration Set'.
    
    Args:
        user_profile: User's profile data
        recipes_df: DataFrame of recipes
        recipe_embeddings: Pre-computed recipe embeddings
        consideration_set_size: Number of recipes to return
        feedback_summary: Optional summarized feedback for preference evolution
        seen_recipe_ids: Set of recipe ID strings already seen by the user (excluded before scoring)
        liked_recipe_names: List of recipe names the user has liked (enriches embedding document)
        disliked_recipe_names: List of recipe names the user has disliked (negative signal in embedding)
    """
    # Generate User Embedding in real-time
    user_document = _create_user_document(user_profile, feedback_summary, liked_recipe_names, disliked_recipe_names)
    user_embedding = embedding_model.encode(user_document).reshape(1, -1)

    print("Generating consideration set with embeddings...")

    # Create a new DataFrame with a simple, sequential integer index to ensure safe embedding lookups
    recipes_to_score_df = recipes_df.reset_index()

    # Filter out already-seen recipes BEFORE scoring so the top-N result is always fresh
    if seen_recipe_ids:
        original_count = len(recipes_to_score_df)
        recipes_to_score_df = recipes_to_score_df[
            ~recipes_to_score_df['recipe_id'].astype(str).isin(seen_recipe_ids)
        ].copy()
        # Re-create a clean integer index so embedding lookups remain correct
        recipe_embeddings = recipe_embeddings[recipes_to_score_df.index.to_numpy()]
        recipes_to_score_df = recipes_to_score_df.reset_index(drop=True)
        print(f"Excluded {original_count - len(recipes_to_score_df)} already-seen recipes before scoring.")

    # Calculate a score for every recipe for the given user by iterating safely
    scores = []
    for i, recipe in recipes_to_score_df.iterrows():
        # Get the specific embedding for this recipe using its integer position
        recipe_embedding = recipe_embeddings[i].reshape(1, -1)
        
        # Calculate score using the modified function
        score = _calculate_score(
            user_profile,
            recipe,
            user_embedding,
            recipe_embedding
        )
        scores.append(score)
    recipes_to_score_df['score'] = scores
    
    # Filter out all recipes that were eliminated (score == 0.0)
    ranked_recipes = recipes_to_score_df[recipes_to_score_df['score'] > 0.0].copy()
    
    # Sort the remaining recipes by the calculated score in descending order
    ranked_recipes.sort_values(by='score', ascending=False, inplace=True)
    
    # Select the top N recipes to form the consideration set
    top_recipes = ranked_recipes.head(consideration_set_size)
    
    print(f"Found {len(top_recipes)} suitable recipes for the consideration set.")
    
    # Format the final list of recipes into the required output structure
    return _format_output(top_recipes)