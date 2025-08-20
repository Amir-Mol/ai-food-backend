import pandas as pd
import numpy as np
import ast
import re
from pathlib import Path
from typing import List, Dict, Any

# Import settings from the central config file
import config

def _parse_ingredients(ingredient_str: str) -> List[str]:
    """
    Parses the complex ingredient string into a clean list of CORE ingredient names.
    """
    COMMON_DESCRIPTORS = {
        'shredded', 'chopped', 'fresh', 'grated', 'uncooked', 'beaten',
        'diced', 'sliced', 'minced', 'crushed', 'ground', 'boneless',
        'skinless', 'large', 'small', 'medium', 'ripe', 'dried', 'canned'
    }
    if not isinstance(ingredient_str, str):
        return []
    try:
        data = ast.literal_eval(ingredient_str)
        if not isinstance(data, dict):
            return []
        all_ingredient_tuples = []
        for section_list in data.values():
            if isinstance(section_list, list):
                all_ingredient_tuples.extend(section_list)
        clean_names = []
        for item in all_ingredient_tuples:
            if isinstance(item, (list, tuple)) and len(item) > 0:
                name = str(item[0])
                name = name.split(',')[0]
                name = name.split(' or ')[0]
                words = name.split()
                core_words = [word for word in words if word.lower() not in COMMON_DESCRIPTORS]
                final_name = ' '.join(core_words).strip()
                if final_name:
                    clean_names.append(final_name)
        return clean_names
    except (ValueError, SyntaxError):
        return []

def _generate_recipe_tags(recipe: pd.Series) -> List[str]:
    """
    Generates a list of objective tags for a recipe based on its nutritional data
    and ingredients.
    """
    tags = []
    # Nutritional Tagging
    if recipe['calories_per_100g [cal]'] <= 40: tags.append('Low Calorie')
    elif recipe['calories_per_100g [cal]'] >= 400: tags.append('High Calorie')
    else: tags.append('Moderate Calorie')
    # ... (add other nutritional tags as needed) ...

    # Dietary Tagging
    ingredient_string = ' '.join(recipe['ingredients_title'])
    pork_keywords = {'pork', 'bacon', 'ham'}
    if any(pork in ingredient_string for pork in pork_keywords):
        tags.append('Contains Pork')
    meat_keywords = {'chicken', 'beef', 'pork', 'lamb', 'turkey', 'fish', 'salmon', 'tuna', 'shrimp', 'crab', 'veal'}
    dairy_egg_keywords = {'milk', 'cheese', 'yogurt', 'butter', 'cream', 'egg'}
    has_meat = any(meat in ingredient_string for meat in meat_keywords)
    has_dairy_egg = any(de in ingredient_string for de in dairy_egg_keywords)
    if not has_meat and not has_dairy_egg:
        tags.append('Vegan')
        tags.append('Vegetarian')
    elif not has_meat:
        tags.append('Vegetarian')
    return tags

def run_preprocessing():
    """
    Executes the full data preprocessing workflow using settings from config.py.
    """
    print("--- Starting Data Preprocessing Workflow ---")
    # 1. Load Raw Data
    print(f"Loading raw data from: {config.RAW_RECIPE_FILE}")
    try:
        df = pd.read_excel(config.RAW_RECIPE_FILE)
    except FileNotFoundError:
        print(f"FATAL ERROR: Input file not found at {config.RAW_RECIPE_FILE}")
        return

    # Standardize column names
    df.columns = df.columns.str.lower().str.replace(r'\[.*\]', '', regex=True).str.strip().str.replace(' ', '_')

    # 2. Data Cleaning
    df.drop_duplicates(subset=['recipe_id'], keep='first', inplace=True)
    nutritional_cols = [
        'calories', 'caloriesfromfat', 'totalfat', 'saturatedfat', 'cholesterol',
        'sodium', 'totalcarbohydrate', 'dietaryfiber', 'sugars', 'protein'
    ]
    for col in nutritional_cols + ['servingsize']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df.dropna(subset=nutritional_cols + ['servingsize'], inplace=True)
    print("Data cleaning complete.")

    # 3. Feature Engineering
    print("Starting feature engineering...")
    df['ingredients_title'] = df['ingredients'].apply(_parse_ingredients)
    
    # Per-serving and per-100g calculations
    for col in nutritional_cols:
        units = config.NUTRITIONAL_UNITS.get(col, 'g')
        df.rename(columns={col: f"{col}_per_serving [{units}]"}, inplace=True)
        per_100g_values = np.where(df['servingsize'] > 0, (df[f"{col}_per_serving [{units}]"] / df['servingsize']) * 100, 0)
        df[f"{col}_per_100g [{units}]"] = np.round(per_100g_values, 1)
    
    # Combined health score
    health_score_cols = ['who_score', 'fsa_score', 'nutri_score']
    normalized_cols = []
    for col in health_score_cols:
        min_val, max_val = df[col].min(), df[col].max()
        norm_col_name = f"{col}_norm"
        df[norm_col_name] = (df[col] - min_val) / (max_val - min_val) if max_val > min_val else 0.5
        normalized_cols.append(norm_col_name)
    df['combined_norm_score'] = df[normalized_cols].mean(axis=1)
    df['health_score'] = np.round((df['combined_norm_score'] * 9) + 1, 1)
    
    # Add placeholder image URL and generate tags
    df['image_url'] = config.PLACEHOLDER_IMAGE_URL
    df['tags'] = df.apply(_generate_recipe_tags, axis=1)
    print("Feature engineering complete.")

    # 4. Finalizing Output
    final_df = df[config.FINAL_COLUMNS]
    config.PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Save to Parquet for the application
    final_df.to_parquet(config.PROCESSED_RECIPE_FILE, index=False)
    print(f"Successfully saved final processed data to: {config.PROCESSED_RECIPE_FILE}")

    # Save to CSV for easy debugging
    final_df.to_csv(config.PROCESSED_RECIPE_DEBUG_CSV_FILE, index=False)
    print(f"Successfully saved debug CSV file to: {config.PROCESSED_RECIPE_DEBUG_CSV_FILE}")

if __name__ == '__main__':
    run_preprocessing()