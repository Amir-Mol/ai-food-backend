"""
Seed the test database with recipe data from CSV.
Run this after Prisma migrations: python tests/seed_test_database.py
"""
import asyncio
import asyncpg
import pandas as pd
import os
from pathlib import Path

# Database connection
DB_URL = "postgresql://testuser:testpassword@localhost:5432/recipe_db_test"

async def seed_recipes():
    """Load recipes from CSV and insert into test database."""
    
    # Connect to database
    conn = await asyncpg.connect(DB_URL)
    
    try:
        # Read recipe CSV
        csv_path = Path(__file__).parent.parent / "data" / "raw" / "pp_recipes(Refined).csv"
        print(f"Reading recipes from: {csv_path}")
        
        if not csv_path.exists():
            print(f"ERROR: Recipe file not found at {csv_path}")
            return
        
        df = pd.read_csv(csv_path)
        print(f"Loaded {len(df)} recipes from CSV")
        
        # Insert recipes into database
        # Assuming Recipe table has: id, name, description, ingredients, instructions
        inserted = 0
        for idx, row in df.iterrows():
            try:
                # Use recipe name as identifier if no ID column
                recipe_name = str(row.get('Name', f'Recipe_{idx}'))
                
                # Insert basic recipe data (adjust columns based on your CSV structure)
                await conn.execute(
                    """
                    INSERT INTO "Recipe" (name, description)
                    VALUES ($1, $2)
                    ON CONFLICT DO NOTHING
                    """,
                    recipe_name,
                    str(row.get('Description', ''))[:500] if 'Description' in row else ''
                )
                inserted += 1
                
                if inserted % 100 == 0:
                    print(f"  Inserted {inserted} recipes...")
                    
            except Exception as e:
                print(f"  Warning: Could not insert recipe {idx}: {e}")
                continue
        
        print(f"✓ Successfully inserted {inserted} recipes")
        
        # Verify
        count = await conn.fetchval('SELECT COUNT(*) FROM "Recipe"')
        print(f"✓ Database now has {count} recipes")
        
    finally:
        await conn.close()

async def main():
    print("=" * 60)
    print("SEEDING TEST DATABASE")
    print("=" * 60)
    await seed_recipes()
    print("=" * 60)
    print("DONE")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
