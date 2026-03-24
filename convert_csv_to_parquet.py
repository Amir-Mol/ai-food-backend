"""
Convert processed_recipes_with_images.csv to processed_recipes.parquet

This simple script loads the corrected CSV and converts it to Parquet format
for production use. Parquet is more efficient (compression, faster loading).
"""

import pandas as pd
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

from config import PROCESSED_RECIPE_FILE

def convert_csv_to_parquet():
    """
    Converts processed_recipes_with_images.csv to processed_recipes.parquet
    """
    # Source and destination paths
    csv_path = Path(__file__).resolve().parent / "data" / "raw" / "processed_recipes_with_images.csv"
    parquet_path = PROCESSED_RECIPE_FILE
    
    print("=" * 80)
    print("CONVERTING CSV TO PARQUET")
    print("=" * 80)
    
    # Load CSV
    print(f"\n📥 Loading CSV from: {csv_path}")
    try:
        df = pd.read_csv(csv_path)
        print(f"   ✓ Loaded {len(df):,} recipes × {len(df.columns)} columns")
    except FileNotFoundError:
        print(f"   ❌ ERROR: File not found at {csv_path}")
        return False
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        return False
    
    # Verify required columns exist
    print(f"\n🔍 Verifying required columns...")
    required_cols = ['recipe_id', 'title', 'image_url', 'health_score', 'who_score', 'fsa_score', 'nutri_score']
    missing_cols = [col for col in required_cols if col not in df.columns]
    
    if missing_cols:
        print(f"   ❌ ERROR: Missing required columns: {missing_cols}")
        return False
    
    print(f"   ✓ All required columns present")
    
    # Check data quality
    print(f"\n📊 Data quality check:")
    print(f"   - Total recipes: {len(df):,}")
    print(f"   - Recipes with images: {df['image_url'].notna().sum():,} ({df['image_url'].notna().sum()/len(df)*100:.1f}%)")
    print(f"   - Health score nulls: {df['health_score'].isna().sum()} ({df['health_score'].isna().sum()/len(df)*100:.1f}%)")
    print(f"   - Health score range: {df['health_score'].min():.1f} - {df['health_score'].max():.1f}")
    
    # Save to Parquet
    print(f"\n💾 Converting and saving to Parquet...")
    try:
        parquet_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(parquet_path, index=False, compression='snappy')
        print(f"   ✓ Successfully saved to: {parquet_path}")
        print(f"\n📈 Parquet file info:")
        print(f"   - Rows: {len(df):,}")
        print(f"   - Columns: {len(df.columns)}")
        print(f"   - File size: ~{parquet_path.stat().st_size / (1024*1024):.2f} MB")
        return True
    except Exception as e:
        print(f"   ❌ ERROR while saving: {e}")
        return False

if __name__ == '__main__':
    success = convert_csv_to_parquet()
    if success:
        print("\n✅ Conversion complete! Ready for embedding generation.")
        sys.exit(0)
    else:
        print("\n❌ Conversion failed.")
        sys.exit(1)
