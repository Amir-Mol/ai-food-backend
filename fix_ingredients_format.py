"""
Fix ingredients_title formatting: Convert string representations to actual lists
"""

import pandas as pd
import ast
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

from config import PROCESSED_RECIPE_FILE

print("=" * 80)
print("FIXING INGREDIENTS_TITLE FORMAT")
print("=" * 80)

print(f"\n📥 Loading parquet...")
df = pd.read_parquet(PROCESSED_RECIPE_FILE)

print(f"Before: ingredients_title type = {type(df['ingredients_title'].iloc[0])}")
print(f"Sample (before): {df['ingredients_title'].iloc[0][:80]}...")

# Convert string representations of lists back to actual lists
def parse_string_list(item):
    """Convert string representation of list to actual list"""
    if isinstance(item, str):
        try:
            # Try to parse as a Python literal (list)
            parsed = ast.literal_eval(item)
            if isinstance(parsed, list):
                return parsed
        except (ValueError, SyntaxError):
            pass
    elif isinstance(item, list):
        return item
    
    # If all else fails, return empty list
    return []

df['ingredients_title'] = df['ingredients_title'].apply(parse_string_list)

print(f"\nAfter: ingredients_title type = {type(df['ingredients_title'].iloc[0])}")
print(f"Sample (after): {df['ingredients_title'].iloc[0]}")

# Verify the conversion worked
if isinstance(df['ingredients_title'].iloc[0], list):
    print(f"✅ Successfully converted to list format")
else:
    print(f"❌ Conversion failed - still type {type(df['ingredients_title'].iloc[0])}")

print(f"\n💾 Saving parquet...")
df.to_parquet(PROCESSED_RECIPE_FILE, index=False, compression='snappy')
print(f"✅ Successfully fixed and saved!")

print("\n" + "=" * 80)
