"""
Dataset Exploration Script
Analyzes the structure and content of the new recipe dataset (processed_recipes_with_images.csv)
"""

import pandas as pd
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

# Load the new dataset
dataset_path = Path(__file__).resolve().parent / "data" / "raw" / "processed_recipes_with_images.csv"

print("=" * 80)
print("EXPLORING NEW DATASET: processed_recipes_with_images.csv")
print("=" * 80)

try:
    df = pd.read_csv(dataset_path)
    
    # Basic Info
    print(f"\n📊 DATASET SIZE: {len(df):,} rows × {len(df.columns)} columns")
    
    # Column Names and Types
    print(f"\n📋 COLUMNS AND DATA TYPES:")
    print("-" * 80)
    for col in df.columns:
        dtype = df[col].dtype
        non_null_count = df[col].notna().sum()
        null_count = df[col].isna().sum()
        null_pct = (null_count / len(df)) * 100
        print(f"  {col:<30} | Type: {str(dtype):<12} | Non-Null: {non_null_count:>8} | Null: {null_count:>8} ({null_pct:>5.1f}%)")
    
    # First 5 rows
    print(f"\n📄 FIRST 5 ROWS:")
    print("-" * 80)
    print(df.head().to_string())
    
    # Statistical Summary
    print(f"\n📈 NUMERICAL COLUMNS SUMMARY:")
    print("-" * 80)
    print(df.describe().to_string())
    
    # Check for key filtering columns
    print(f"\n🔍 KEY FILTERING COLUMNS ANALYSIS:")
    print("-" * 80)
    
    # number_of_ratings
    if 'number_of_ratings' in df.columns:
        print(f"\n  'number_of_ratings' (Popularity Filter)")
        print(f"    - Range: {df['number_of_ratings'].min()} to {df['number_of_ratings'].max()}")
        print(f"    - Recipes with >= 3 ratings: {(df['number_of_ratings'] >= 3).sum():,} ({(df['number_of_ratings'] >= 3).sum()/len(df)*100:.1f}%)")
    else:
        print(f"\n  ⚠️  'number_of_ratings' column NOT found")
    
    # average_rating
    if 'average_rating' in df.columns:
        print(f"\n  'average_rating' (Quality Filter)")
        print(f"    - Range: {df['average_rating'].min():.2f} to {df['average_rating'].max():.2f}")
        print(f"    - Recipes with >= 3 rating: {(df['average_rating'] >= 3).sum():,} ({(df['average_rating'] >= 3).sum()/len(df)*100:.1f}%)")
    else:
        print(f"\n  ⚠️  'average_rating' column NOT found")
    
    # image_url
    if 'image_url' in df.columns:
        has_image = df['image_url'].notna().sum()
        print(f"\n  'image_url'")
        print(f"    - Recipes WITH images: {has_image:,} ({has_image/len(df)*100:.1f}%)")
        print(f"    - Recipes WITHOUT images: {len(df) - has_image:,}")
    else:
        print(f"\n  ⚠️  'image_url' column NOT found")
    
    # Check for health score columns
    health_cols = ['who_score', 'fsa_score', 'nutri_score']
    print(f"\n  Health Score Columns:")
    for col in health_cols:
        if col in df.columns:
            print(f"    ✓ '{col}' exists - Non-null: {df[col].notna().sum():,}")
        else:
            print(f"    ✗ '{col}' NOT found")
    
    # Combined filtering impact
    print(f"\n🔗 COMBINED FILTERING IMPACT:")
    print("-" * 80)
    
    # Apply all filters
    filtered = df.copy()
    
    # Filter 1: number_of_ratings >= 3
    if 'number_of_ratings' in filtered.columns:
        count_before = len(filtered)
        filtered = filtered[filtered['number_of_ratings'] >= 3]
        print(f"  After number_of_ratings >= 3: {len(filtered):,} recipes (removed {count_before - len(filtered):,})")
    
    # Filter 2: average_rating >= 3
    if 'average_rating' in filtered.columns:
        count_before = len(filtered)
        filtered = filtered[filtered['average_rating'] >= 3]
        print(f"  After average_rating >= 3:     {len(filtered):,} recipes (removed {count_before - len(filtered):,})")
    
    # Filter 3: Has image_url
    if 'image_url' in filtered.columns:
        count_before = len(filtered)
        filtered = filtered[filtered['image_url'].notna()]
        print(f"  After filtering for images:    {len(filtered):,} recipes (removed {count_before - len(filtered):,})")
    
    print(f"\n  📊 Final dataset size after all filters: {len(filtered):,} recipes")
    print(f"     Reduction: {len(df) - len(filtered):,} recipes removed ({(len(df) - len(filtered))/len(df)*100:.1f}%)")
    
    # Sample of filtered data
    if len(filtered) > 0:
        print(f"\n📄 SAMPLE OF FILTERED DATA (first 3 rows):")
        print("-" * 80)
        print(filtered.head(3).to_string())
    
except FileNotFoundError:
    print(f"\n❌ ERROR: File not found at {dataset_path}")
    print(f"   Please make sure processed_recipes_with_images.csv is in: {dataset_path.parent}")
except Exception as e:
    print(f"\n❌ ERROR: {e}")

print("\n" + "=" * 80)
