import asyncio
from database import db
import json

async def erase_all_data():
    """
    Deletes all records from TrainingRecord and User tables.
    USE WITH CAUTION. FOR DEVELOPMENT DATABASE ONLY.
    """
    print("\n--- ERASING ALL DATA ---")
    
    # Delete from child tables first to avoid foreign key violations
    deleted_records_count = await db.trainingrecord.delete_many()
    print(f"Deleted {deleted_records_count} training record entries.")
    
    # Now delete from the parent table
    deleted_users_count = await db.user.delete_many()
    print(f"Deleted {deleted_users_count} user entries.")
    
    print("All user data has been erased.")

async def check_users_in_db():
    """
    Connects to the database, fetches all users, and prints their details.
    """
    users = await db.user.find_many()
    if not users:
        print("\nNo users found in the database.")
        return
    print(f"\n--- Found {len(users)} User(s) ---")
    for user in users:
        print(f"\n- User ID: {user.id}")
        print(f"  Email: {user.email}")
        print(f"  A/B Test Group: {user.group}")
        print(f"  Onboarding Completed: {user.onboardingCompleted}")
        
        # --- Section to print the full profile ---
        print(f"  --- Basic Profile ---")
        print(f"  Name: {user.name}")
        print(f"  Age: {user.age}")
        print(f"  Gender: {user.gender}")
        print(f"  Height: {user.height} {user.heightUnit or ''}")
        print(f"  Weight: {user.weight} {user.weightUnit or ''}")
        print(f"  Activity Level: {user.activityLevel}")
        
        print(f"  --- Dietary Profile ---")
        dietary_profile_json = json.dumps(user.dietaryProfile, indent=2) if user.dietaryProfile else "Not set"
        print(f"  {dietary_profile_json}")
        
        print(f"  --- Taste Profile ---")
        print(f"  Liked Ingredients: {user.likedIngredients}")
        print(f"  Disliked Ingredients: {user.dislikedIngredients}")
        print(f"  Favorite Cuisines: {user.favoriteCuisines}")
        print(f"  Other Cuisine: {user.otherCuisine}")
        
async def check_training_records_in_db():
    """
    Connects to the database, fetches all training records, and prints the details.
    """
    records = await db.trainingrecord.find_many(order={'createdAt': 'desc'})
    if not records:
        print("\nNo training records found in the database.")
        return
    print(f"\n--- Found {len(records)} Training Record(s) ---")
    for record in records:
        print(f"\n- Record ID: {record.id} | Created: {record.createdAt.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  User ID: {record.userId}")
        print(f"  Recommendation: '{record.recommendationName}' ({record.recommendationId})")
        print(f"  Feedback -> Liked: {record.liked}, Health: {record.healthinessScore}, Taste: {record.tastinessScore}, Intent: {record.intentToTryScore}")

async def main():
    """
    Main function to connect to the DB and run checks.
    """
    print("Connecting to database...")
    await db.connect()
    print("Database connected.")
    try:
        # --- To erase all data, uncomment the line below and run the script ---
        #await erase_all_data()

        await check_users_in_db()
        #await check_training_records_in_db()
    finally:
        print("\nDisconnecting from database...")
        await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())