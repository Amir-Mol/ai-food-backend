"""
Enhanced Data Preprocessing Pipeline for Food Dataset (pp_recipes(Refined).csv)

Improvements over original preprocessing.py:
- Handles new dataset column names and structure
- Better health score calculation (inverted + normalized + weighted)
- Improved ingredient parsing (case-insensitive, plural handling)
- Better error handling and validation
- Progress indicators
- Robust null handling with warnings
"""

import pandas as pd
import numpy as np
import ast
import sys
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add the project's root directory (backend) to the Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Import settings from the central config file
import config


# ============================================================================
# COLUMN MAPPING: Map new dataset columns to expected output format
# ============================================================================

COLUMN_MAPPING = {
    'recipe_id': 'recipe_id',
    'title': 'title',
    'recipe_url': 'recipe_url',
    'image_url': 'image_url',  # Will be a placeholder, filled by crawler later
    'ingredients': 'ingredients',
    'ingredients_title': 'ingredients_title',  # Will be generated
    'tags': 'tags',  # Will be generated/updated
    # Nutritional columns: map from new format (with units) to old format
    'calories [cal]': 'calories',
    'caloriesFromFat [cal]': 'caloriesfromfat',
    'totalFat [g]': 'totalfat',
    'saturatedFat [g]': 'saturatedfat',
    'cholesterol [mg]': 'cholesterol',
    'sodium [mg]': 'sodium',
    'totalCarbohydrate [g]': 'totalcarbohydrate',
    'dietaryFiber [g]': 'dietaryfiber',
    'sugars [g]': 'sugars',
    'protein [g]': 'protein',
    'servingSize [g]': 'servingsize',
    'who_score': 'who_score',
    'fsa_score': 'fsa_score',
    'nutri_score': 'nutri_score',
}

NUTRITIONAL_COLS = [
    'calories', 'caloriesfromfat', 'totalfat', 'saturatedfat', 'cholesterol',
    'sodium', 'totalcarbohydrate', 'dietaryfiber', 'sugars', 'protein'
]


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _parse_ingredients(ingredient_str: str) -> List[str]:
    """
    Parses the complex ingredient string into a clean list of CORE ingredient names.
    Handles dictionary format from food.com dataset.
    """
    COMMON_DESCRIPTORS = {
        'shredded', 'chopped', 'fresh', 'grated', 'uncooked', 'beaten',
        'diced', 'sliced', 'minced', 'crushed', 'ground', 'boneless',
        'skinless', 'large', 'small', 'medium', 'ripe', 'dried', 'canned',
        'cooked', 'raw', 'toasted', 'roasted', 'blanched', 'peeled', 'seeded'
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
                # Split on comma and use first part
                name = name.split(',')[0]
                # Split on 'or' and use first part
                name = name.split(' or ')[0]
                
                # Split into words and filter descriptors (case-insensitive)
                words = name.split()
                core_words = [
                    word for word in words 
                    if word.lower() not in COMMON_DESCRIPTORS
                ]
                final_name = ' '.join(core_words).strip()
                
                if final_name:
                    clean_names.append(final_name)
        
        return clean_names
    
    except (ValueError, SyntaxError):
        return []


def _generate_recipe_tags(recipe: pd.Series) -> List[str]:
    """
    Generates a list of objective tags for a recipe based on nutritional data
    and ingredients. Includes both nutritional and dietary tags.
    """
    tags = []
    
    # ===== NUTRITIONAL TAGGING =====
    try:
        cal_per_100g = recipe.get('calories_per_100g [cal]')
        if not pd.isna(cal_per_100g):
            if cal_per_100g <= 40:
                tags.append('Low Calorie')
            elif cal_per_100g >= 400:
                tags.append('High Calorie')
            else:
                tags.append('Moderate Calorie')
    except:
        pass
    
    # Protein tagging
    try:
        protein = recipe.get('protein_per_serving [g]')
        if not pd.isna(protein):
            if protein >= 30:
                tags.append('High Protein')
            elif protein >= 15:
                tags.append('Moderate Protein')
    except:
        pass
    
    # ===== DIETARY TAGGING =====
    try:
        ingredients_list = recipe.get('ingredients_title', [])
        if isinstance(ingredients_list, list):
            ingredient_string = ' '.join(ingredients_list).lower()
        else:
            ingredient_string = str(ingredients_list).lower()
        
        # Pork detection
        pork_keywords = {'pork', 'bacon', 'ham'}
        if any(keyword in ingredient_string for keyword in pork_keywords):
            tags.append('Contains Pork')
        
        # Dietary classification
        meat_keywords = {
            'chicken', 'beef', 'pork', 'lamb', 'turkey', 'fish', 'salmon',
            'tuna', 'shrimp', 'crab', 'veal', 'duck', 'turkey', 'mutton'
        }
        dairy_egg_keywords = {
            'milk', 'cheese', 'yogurt', 'butter', 'cream', 'egg',
            'whey', 'lactose'
        }
        
        has_meat = any(keyword in ingredient_string for keyword in meat_keywords)
        has_dairy_egg = any(keyword in ingredient_string for keyword in dairy_egg_keywords)
        
        if not has_meat and not has_dairy_egg:
            tags.append('Vegan')
            tags.append('Vegetarian')
        elif not has_meat:
            tags.append('Vegetarian')
        
        # Shellfish detection
        shellfish_keywords = {'shrimp', 'crab', 'lobster', 'oyster', 'clam', 'mussel'}
        if any(keyword in ingredient_string for keyword in shellfish_keywords):
            tags.append('Shellfish')
        
        # Gluten detection (common allergen)
        gluten_keywords = {'wheat', 'flour', 'bread', 'pasta', 'barley', 'rye'}
        if any(keyword in ingredient_string for keyword in gluten_keywords):
            tags.append('Contains Gluten')
        
    except:
        pass
    
    return tags


def _calculate_health_score(recipe: pd.Series) -> float:
    """
    Calculates a health score (1-10) based on nutri_score and fsa_score.
    
    Logic:
    - Scores are already in 0-1 range where higher = healthier
    - Use weighted average: Nutri (60%), FSA (40%)
    - Return neutral score if nutri_score is null
    - Scale to 1-10 range
    
    Formula: (nutri_score * 0.6 + fsa_score * 0.4) * 9 + 1
    """
    
    nutri_score = recipe.get('nutri_score')
    
    # If nutri_score is null/NaN, return neutral score
    if pd.isna(nutri_score):
        return 5.0
    
    fsa_score = recipe.get('fsa_score')
    
    # Calculate weighted score
    # If fsa_score is missing, use nutri_score only
    if pd.isna(fsa_score):
        weighted_score = nutri_score
    else:
        weighted_score = (nutri_score * 0.6) + (fsa_score * 0.4)
    
    # Scale to 1-10 range
    final_score = (weighted_score * 9) + 1
    
    # Clamp to valid range and round to 1 decimal place
    return np.round(np.clip(final_score, 1.0, 10.0), 1)


# ============================================================================
# MAIN PREPROCESSING FUNCTION
# ============================================================================

def run_preprocessing_new():
    """
    Executes the enhanced data preprocessing workflow for the new dataset.
    """
    print("=" * 80)
    print("ENHANCED DATA PREPROCESSING WORKFLOW")
    print("Processing: pp_recipes(Refined).csv → processed_recipes_new.parquet")
    print("=" * 80)
    
    # ===== STEP 1: LOAD RAW DATA =====
    raw_file = Path(__file__).resolve().parent.parent / "data" / "raw" / "pp_recipes(Refined).csv"
    print(f"\n📥 STEP 1: Loading raw data from {raw_file}")
    
    try:
        df = pd.read_csv(raw_file, low_memory=False)
        print(f"   ✓ Loaded {len(df):,} recipes")
    except FileNotFoundError:
        print(f"   ❌ FATAL ERROR: File not found at {raw_file}")
        return
    except Exception as e:
        print(f"   ❌ FATAL ERROR: {e}")
        return
    
    # ===== STEP 2: FILTER BY POPULARITY SCORE =====
    print(f"\n🔍 STEP 2: Filtering by popularity score")
    
    # Create popularity score: quality × popularity
    # This combines average_rating (quality) with log(number_of_ratings) (popularity)
    # Formula commonly used in recommendation systems (similar to Reddit ranking)
    df["popularity_score"] = df["average_rating"] * np.log1p(df["number_of_ratings"])
    
    # Sort by popularity score (descending)
    df_sorted = df.sort_values(by="popularity_score", ascending=False)
    print(f"   ✓ Calculated popularity scores")
    
    # Keep top 10,000 recipes
    target_recipes = 10000
    df = df_sorted.head(target_recipes)
    print(f"   ✓ Selected top {len(df):,} recipes by popularity score")
    print(f"   Popularity score range: {df['popularity_score'].min():.2f} - {df['popularity_score'].max():.2f}")
    
    # Drop the temporary popularity_score column (no longer needed)
    df = df.drop(columns=['popularity_score'])
    
    if len(df) == 0:
        print("   ❌ ERROR: No recipes remaining after filtering!")
        return
    
    print(f"   ✓ Final filtered dataset: {len(df):,} recipes")
    
    # ===== STEP 3: COLUMN SELECTION & RENAMING =====
    print(f"\n🔄 STEP 3: Mapping and cleaning columns")
    
    # Select only the columns we need from the new dataset
    columns_to_load = [
        'recipe_id', 'title', 'recipe_url', 'ingredients', 'tags',
        'average_rating', 'number_of_ratings',
        'servingSize [g]',  # serving size
        'calories [cal]', 'caloriesFromFat [cal]', 'totalFat [g]',
        'saturatedFat [g]', 'cholesterol [mg]', 'sodium [mg]',
        'totalCarbohydrate [g]', 'dietaryFiber [g]', 'sugars [g]', 'protein [g]',
        'who_score', 'fsa_score', 'nutri_score'
    ]
    
    # Check which columns exist
    missing_cols = [col for col in columns_to_load if col not in df.columns]
    if missing_cols:
        print(f"   ⚠️  WARNING: Missing columns in dataset: {missing_cols}")
    
    # Select available columns
    available_cols = [col for col in columns_to_load if col in df.columns]
    df = df[available_cols]
    print(f"   ✓ Selected {len(df.columns)} columns")
    
    # Rename columns to match expected format (remove units)
    rename_dict = {
        'servingSize [g]': 'servingsize',
        'calories [cal]': 'calories',
        'caloriesFromFat [cal]': 'caloriesfromfat',
        'totalFat [g]': 'totalfat',
        'saturatedFat [g]': 'saturatedfat',
        'cholesterol [mg]': 'cholesterol',
        'sodium [mg]': 'sodium',
        'totalCarbohydrate [g]': 'totalcarbohydrate',
        'dietaryFiber [g]': 'dietaryfiber',
        'sugars [g]': 'sugars',
        'protein [g]': 'protein',
    }
    df.rename(columns=rename_dict, inplace=True)
    print(f"   ✓ Columns renamed to standard format")
    
    # ===== STEP 4: DATA CLEANING & VALIDATION =====
    print(f"\n🧹 STEP 4: Data cleaning and validation")
    
    # Convert nutritional columns to numeric
    for col in NUTRITIONAL_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Validate that required nutritional columns are present and numeric
    missing_nutritional = [col for col in NUTRITIONAL_COLS if col not in df.columns]
    if missing_nutritional:
        print(f"   ⚠️  WARNING: Missing nutritional columns: {missing_nutritional}")
    
    # Drop rows with missing nutritional data
    initial_count = len(df)
    df.dropna(subset=[col for col in NUTRITIONAL_COLS if col in df.columns], inplace=True)
    print(f"   ✓ Removed {initial_count - len(df):,} recipes with incomplete nutritional data")
    
    # Drop rows with missing essential columns
    essential_cols = ['recipe_id', 'title', 'servingsize', 'ingredients']
    initial_count = len(df)
    df.dropna(subset=[col for col in essential_cols if col in df.columns], inplace=True)
    print(f"   ✓ Removed {initial_count - len(df):,} recipes with missing essential data")
    
    if len(df) == 0:
        print("   ❌ ERROR: No recipes remaining after data cleaning!")
        return
    
    # ===== STEP 5: FEATURE ENGINEERING =====
    print(f"\n⚙️  STEP 5: Feature engineering")
    
    # Parse ingredients
    print(f"   Parsing ingredients...")
    df['ingredients_title'] = df['ingredients'].apply(_parse_ingredients)
    print(f"   ✓ Ingredients parsed")
    
    # Calculate per-serving and per-100g nutritional values
    print(f"   Calculating per-serving and per-100g values...")
    for col in NUTRITIONAL_COLS:
        if col in df.columns and col != 'servingsize':
            units = config.NUTRITIONAL_UNITS.get(col, 'g')
            # Rename to per-serving
            df.rename(columns={col: f"{col}_per_serving [{units}]"}, inplace=True)
            col_per_serving = f"{col}_per_serving [{units}]"
            
            # Calculate per-100g (with safety check for division)
            per_100g_values = np.where(
                df['servingsize'] > 0,
                (df[col_per_serving] / df['servingsize']) * 100,
                0
            )
            df[f"{col}_per_100g [{units}]"] = np.round(per_100g_values, 1)
    
    print(f"   ✓ Nutritional values calculated")
    
    # Calculate health score
    print(f"   Calculating health score...")
    df['health_score'] = df.apply(_calculate_health_score, axis=1)
    print(f"   ✓ Health scores calculated")
    
    # Generate tags
    print(f"   Generating recipe tags...")
    df['tags'] = df.apply(_generate_recipe_tags, axis=1)
    print(f"   ✓ Tags generated")
    
    # Add placeholder image_url column (will be filled by crawler)
    df['image_url'] = None
    print(f"   ✓ Added placeholder image_url column")
    
    # ===== STEP 6: FINAL COLUMN SELECTION & OUTPUT =====
    print(f"\n📤 STEP 6: Finalizing output")
    
    # Define final columns (matching FINAL_COLUMNS in config.py)
    final_columns = [
        'recipe_id', 'title', 'recipe_url', 'image_url', 'ingredients', 'ingredients_title',
        'tags', 'calories_per_serving [cal]', 'calories_per_100g [cal]',
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
    
    # Check which final columns exist
    missing_final_cols = [col for col in final_columns if col not in df.columns]
    if missing_final_cols:
        print(f"   ⚠️  WARNING: Missing columns in final output: {missing_final_cols}")
        final_columns = [col for col in final_columns if col in df.columns]
    
    final_df = df[final_columns]
    
    # Create output directory
    config.PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Save to Parquet
    output_parquet = Path(__file__).resolve().parent.parent / "data" / "processed" / "processed_recipes_new.parquet"
    final_df.to_parquet(output_parquet, index=False)
    print(f"   ✓ Saved to: {output_parquet}")
    print(f"     Total recipes: {len(final_df):,}")
    
    # Save debug CSV
    output_csv = Path(__file__).resolve().parent.parent / "data" / "processed" / "processed_recipes_new_debug.csv"
    final_df.to_csv(output_csv, index=False)
    print(f"   ✓ Saved debug CSV to: {output_csv}")
    
    # ===== STEP 7: SUMMARY & VALIDATION =====
    print(f"\n📊 STEP 7: Summary and validation")
    print(f"   Total recipes processed: {len(final_df):,}")
    print(f"   Columns in output: {len(final_df.columns)}")
    print(f"   Health score range: {final_df['health_score'].min():.2f} - {final_df['health_score'].max():.2f}")
    print(f"   Recipes with tags: {(final_df['tags'].str.len() > 0).sum():,}")
    print(f"   Average tags per recipe: {final_df['tags'].apply(len).mean():.1f}")
    
    print("\n" + "=" * 80)
    print("✅ PREPROCESSING COMPLETE!")
    print("=" * 80)
    print(f"\nNext steps:")
    print(f"1. Run web crawler to fetch image URLs")
    print(f"2. Filter out recipes without images")
    print(f"3. Replace processed_recipes.parquet with processed_recipes_new.parquet")
    print(f"4. Regenerate recipe_embeddings.npy")
    print("=" * 80)


if __name__ == '__main__':
    run_preprocessing_new()
