from pathlib import Path

# --- Core Paths ---
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"

# --- File Paths ---
RAW_RECIPE_FILE = RAW_DATA_DIR / "Recipe_fooddotcom.xlsx"
PROCESSED_RECIPE_FILE = PROCESSED_DATA_DIR / "processed_recipes.parquet"
PROCESSED_RECIPE_DEBUG_CSV_FILE = PROCESSED_DATA_DIR / "processed_recipes_debug.csv"
RECIPE_EMBEDDINGS_FILE = PROCESSED_DATA_DIR / "recipe_embeddings.npy"

# Exact list of cleaned nutritional column names from the raw data
NUTRITIONAL_COLS = [
    'calories', 'caloriesfromfat', 'totalfat', 'saturatedfat', 'cholesterol',
    'sodium', 'totalcarbohydrate', 'dietaryfiber', 'sugars', 'protein'
]

# Units for final column renaming (default is 'g')
NUTRITIONAL_UNITS = {
    'calories': 'cal', 'caloriesfromfat': 'cal', 'cholesterol': 'mg', 'sodium': 'mg'
}

# The final, exact list of columns to keep in the processed output file
FINAL_COLUMNS = [
    'recipe_id', 'title', 'recipe_url', 'image_url', 'ingredients', 'ingredients_title',
    'tags','calories_per_serving [cal]', 'calories_per_100g [cal]',
    'caloriesfromfat_per_serving [cal]', 'caloriesfromfat_per_100g [cal]',
    'totalfat_per_serving [g]', 'totalfat_per_100g [g]',
    'saturatedfat_per_serving [g]', 'saturatedfat_per_100g [g]',
    'cholesterol_per_serving [mg]', 'cholesterol_per_100g [mg]',
    'sodium_per_serving [mg]', 'sodium_per_100g [mg]',
    'totalcarbohydrate_per_serving [g]', 'totalcarbohydrate_per_100g [g]',
    'dietaryfiber_per_serving [g]', 'dietaryfiber_per_100g [g]',
    'sugars_per_serving [g]', 'sugars_per_100g [g]',
    'protein_per_serving [g]', 'protein_per_100g [g]',
    'who_score', 'fsa_score', 'nutri_score', 'health_score'
]