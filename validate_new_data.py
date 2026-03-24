"""
Validation Script: Compare new and old recipe data files

This script validates that the new processed_recipes.parquet and recipe_embeddings.npy
have the same structure as the old versions, with more data (more rows/recipes).

Checks performed:
1. Parquet column names match
2. Parquet column data types match
3. Parquet has more rows
4. Embeddings have same dimensions (columns/features)
5. Embeddings have more rows (recipes)
6. New files are non-empty and loadable
"""

import pandas as pd
import numpy as np
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

from config import PROCESSED_DATA_DIR

def validate_parquet_files():
    """
    Compares old and new parquet files for structural compatibility.
    """
    print("=" * 80)
    print("VALIDATING PARQUET FILES")
    print("=" * 80)
    
    old_path = PROCESSED_DATA_DIR / "processed_recipes_old.parquet"
    new_path = PROCESSED_DATA_DIR / "processed_recipes.parquet"
    
    # Load old file
    print(f"\n📥 Loading old parquet: {old_path}")
    try:
        df_old = pd.read_parquet(old_path)
        print(f"   ✓ Loaded {len(df_old):,} recipes × {len(df_old.columns)} columns")
    except FileNotFoundError:
        print(f"   ⚠️  WARNING: Old parquet file not found (this is OK for first migration)")
        df_old = None
    except Exception as e:
        print(f"   ❌ ERROR loading old parquet: {e}")
        return False
    
    # Load new file
    print(f"\n📥 Loading new parquet: {new_path}")
    try:
        df_new = pd.read_parquet(new_path)
        print(f"   ✓ Loaded {len(df_new):,} recipes × {len(df_new.columns)} columns")
    except FileNotFoundError:
        print(f"   ❌ ERROR: New parquet file not found!")
        return False
    except Exception as e:
        print(f"   ❌ ERROR loading new parquet: {e}")
        return False
    
    if df_old is None:
        print("\n⚠️  Skipping structural comparison (no old file)")
        return True
    
    # Check 1: Column names match
    print(f"\n🔍 CHECK 1: Column names")
    if set(df_old.columns) == set(df_new.columns):
        print(f"   ✅ Column names match ({len(df_old.columns)} columns)")
    else:
        missing_in_new = set(df_old.columns) - set(df_new.columns)
        extra_in_new = set(df_new.columns) - set(df_old.columns)
        if missing_in_new:
            print(f"   ❌ Missing in new: {missing_in_new}")
        if extra_in_new:
            print(f"   ⚠️  Extra in new: {extra_in_new}")
        return False
    
    # Check 2: Column data types match
    print(f"\n🔍 CHECK 2: Column data types")
    dtype_mismatch = []
    for col in df_old.columns:
        if df_old[col].dtype != df_new[col].dtype:
            dtype_mismatch.append((col, df_old[col].dtype, df_new[col].dtype))
    
    if not dtype_mismatch:
        print(f"   ✅ All data types match")
    else:
        print(f"   ⚠️  Data type mismatches found:")
        for col, old_dtype, new_dtype in dtype_mismatch:
            print(f"      - {col}: {old_dtype} → {new_dtype}")
        print(f"      (This may be OK depending on the changes)")
    
    # Check 3: Row count increased
    print(f"\n🔍 CHECK 3: Row count comparison")
    old_count = len(df_old)
    new_count = len(df_new)
    increase = new_count - old_count
    increase_pct = (increase / old_count * 100) if old_count > 0 else 0
    
    if new_count >= old_count:
        print(f"   ✅ Row count increased or stayed same")
        print(f"      Old: {old_count:,} recipes")
        print(f"      New: {new_count:,} recipes")
        print(f"      Increase: +{increase:,} ({increase_pct:.1f}%)")
    else:
        print(f"   ❌ ERROR: New file has fewer rows!")
        print(f"      Old: {old_count:,} recipes")
        print(f"      New: {new_count:,} recipes")
        return False
    
    # Check 4: Sample data validation
    print(f"\n🔍 CHECK 4: Sample data validation")
    required_cols = ['recipe_id', 'title', 'image_url', 'health_score', 'who_score', 'fsa_score', 'nutri_score']
    missing = [col for col in required_cols if col not in df_new.columns]
    
    if not missing:
        print(f"   ✅ All required columns present")
        print(f"      - Recipes with images: {df_new['image_url'].notna().sum():,} / {new_count:,} ({df_new['image_url'].notna().sum()/new_count*100:.1f}%)")
        print(f"      - Health score range: {df_new['health_score'].min():.1f} - {df_new['health_score'].max():.1f}")
        print(f"      - Health score nulls: {df_new['health_score'].isna().sum()}")
    else:
        print(f"   ❌ Missing required columns: {missing}")
        return False
    
    return True


def validate_embeddings_files():
    """
    Compares old and new embeddings (NPY) files for structural compatibility.
    """
    print("\n" + "=" * 80)
    print("VALIDATING EMBEDDINGS FILES")
    print("=" * 80)
    
    old_path = PROCESSED_DATA_DIR / "recipe_embeddings_old.npy"
    new_path = PROCESSED_DATA_DIR / "recipe_embeddings.npy"
    
    # Load old embeddings
    print(f"\n📥 Loading old embeddings: {old_path}")
    try:
        embeddings_old = np.load(old_path)
        print(f"   ✓ Loaded embeddings with shape: {embeddings_old.shape}")
        print(f"     - Recipes: {embeddings_old.shape[0]:,}")
        print(f"     - Dimensions: {embeddings_old.shape[1]}")
        print(f"     - Data type: {embeddings_old.dtype}")
    except FileNotFoundError:
        print(f"   ⚠️  WARNING: Old embeddings file not found (this is OK for first migration)")
        embeddings_old = None
    except Exception as e:
        print(f"   ❌ ERROR loading old embeddings: {e}")
        return False
    
    # Load new embeddings
    print(f"\n📥 Loading new embeddings: {new_path}")
    try:
        embeddings_new = np.load(new_path)
        print(f"   ✓ Loaded embeddings with shape: {embeddings_new.shape}")
        print(f"     - Recipes: {embeddings_new.shape[0]:,}")
        print(f"     - Dimensions: {embeddings_new.shape[1]}")
        print(f"     - Data type: {embeddings_new.dtype}")
    except FileNotFoundError:
        print(f"   ❌ ERROR: New embeddings file not found!")
        return False
    except Exception as e:
        print(f"   ❌ ERROR loading new embeddings: {e}")
        return False
    
    if embeddings_old is None:
        print("\n⚠️  Skipping structural comparison (no old file)")
        return True
    
    # Check 1: Dimensions (features) match
    print(f"\n🔍 CHECK 1: Embedding dimensions")
    if embeddings_old.shape[1] == embeddings_new.shape[1]:
        dims = embeddings_new.shape[1]
        print(f"   ✅ Dimensions match: {dims} features")
    else:
        print(f"   ❌ ERROR: Dimension mismatch!")
        print(f"      Old: {embeddings_old.shape[1]} features")
        print(f"      New: {embeddings_new.shape[1]} features")
        return False
    
    # Check 2: Data type matches
    print(f"\n🔍 CHECK 2: Data type")
    if embeddings_old.dtype == embeddings_new.dtype:
        print(f"   ✅ Data type matches: {embeddings_new.dtype}")
    else:
        print(f"   ⚠️  Data type differs:")
        print(f"      Old: {embeddings_old.dtype}")
        print(f"      New: {embeddings_new.dtype}")
        print(f"      (This may cause issues with loading)")
        return False
    
    # Check 3: Row count increased
    print(f"\n🔍 CHECK 3: Row count comparison")
    old_count = embeddings_old.shape[0]
    new_count = embeddings_new.shape[0]
    increase = new_count - old_count
    increase_pct = (increase / old_count * 100) if old_count > 0 else 0
    
    if new_count >= old_count:
        print(f"   ✅ Row count increased or stayed same")
        print(f"      Old: {old_count:,} embeddings")
        print(f"      New: {new_count:,} embeddings")
        print(f"      Increase: +{increase:,} ({increase_pct:.1f}%)")
    else:
        print(f"   ❌ ERROR: New file has fewer embeddings!")
        print(f"      Old: {old_count:,}")
        print(f"      New: {new_count:,}")
        return False
    
    # Check 4: Embedding vectors are valid (not NaN/Inf)
    print(f"\n🔍 CHECK 4: Embedding validity")
    nan_count = np.isnan(embeddings_new).sum()
    inf_count = np.isinf(embeddings_new).sum()
    
    if nan_count == 0 and inf_count == 0:
        print(f"   ✅ All embeddings are valid (no NaN/Inf values)")
    else:
        print(f"   ❌ ERROR: Invalid values found!")
        print(f"      NaN values: {nan_count}")
        print(f"      Inf values: {inf_count}")
        return False
    
    return True


def validate_consistency():
    """
    Verifies that parquet row count matches embeddings row count.
    """
    print("\n" + "=" * 80)
    print("VALIDATING CONSISTENCY BETWEEN FILES")
    print("=" * 80)
    
    new_parquet_path = PROCESSED_DATA_DIR / "processed_recipes.parquet"
    new_embeddings_path = PROCESSED_DATA_DIR / "recipe_embeddings.npy"
    
    print(f"\n📥 Loading new parquet...")
    try:
        df_new = pd.read_parquet(new_parquet_path)
        parquet_rows = len(df_new)
        print(f"   ✓ Parquet rows: {parquet_rows:,}")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        return False
    
    print(f"\n📥 Loading new embeddings...")
    try:
        embeddings_new = np.load(new_embeddings_path)
        embeddings_rows = embeddings_new.shape[0]
        print(f"   ✓ Embeddings rows: {embeddings_rows:,}")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        return False
    
    print(f"\n🔍 CHECK: Row count consistency")
    if parquet_rows == embeddings_rows:
        print(f"   ✅ Parquet and embeddings have matching row counts: {parquet_rows:,}")
        return True
    else:
        print(f"   ❌ ERROR: Mismatch between parquet and embeddings!")
        print(f"      Parquet rows: {parquet_rows:,}")
        print(f"      Embeddings rows: {embeddings_rows:,}")
        return False


def main():
    """
    Runs all validation checks.
    """
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "  DATA VALIDATION: New vs Old Files".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "=" * 78 + "╝")
    
    result_parquet = validate_parquet_files()
    result_embeddings = validate_embeddings_files()
    result_consistency = validate_consistency()
    
    # Final summary
    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)
    
    status = {
        "Parquet validation": "✅ PASS" if result_parquet else "❌ FAIL",
        "Embeddings validation": "✅ PASS" if result_embeddings else "❌ FAIL",
        "Consistency check": "✅ PASS" if result_consistency else "❌ FAIL",
    }
    
    for check, result in status.items():
        print(f"{check:<30} {result}")
    
    overall = result_parquet and result_embeddings and result_consistency
    
    print("\n" + "=" * 80)
    if overall:
        print("🎉 ALL VALIDATIONS PASSED! Files are safe to deploy.")
        print("=" * 80)
        return 0
    else:
        print("⚠️  VALIDATION FAILED! Review errors above before deploying.")
        print("=" * 80)
        return 1


if __name__ == '__main__':
    sys.exit(main())
