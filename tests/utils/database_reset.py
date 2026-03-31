"""
Database utilities for testing.
Provides functions to reset and manage test database state.
"""

import asyncio
from database import db


async def reset_test_database():
    """
    Reset test database to clean state.
    
    - Keeps recipe data (seeds intact)
    - Clears User and TrainingRecord tables
    - Clears Feedback table
    - Clears TrainingRecord table
    """
    try:
        print("\n[DB Reset] Starting database cleanup...")
        
        # Clear TrainingRecord (must come first due to foreign key)
        deleted_records = await db.trainingrecord.delete_many(where={})
        print(f"[DB Reset] Deleted {deleted_records} TrainingRecord entries")
        
        # Clear Feedback
        deleted_feedback = await db.feedback.delete_many(where={})
        print(f"[DB Reset] Deleted {deleted_feedback} Feedback entries")
        
        # Clear User (except admin)
        deleted_users = await db.user.delete_many(
            where={"email": {"not": "admin@example.com"}}
        )
        print(f"[DB Reset] Deleted {deleted_users} User entries")
        
        print("[DB Reset] Database cleanup complete!\n")
        return True
        
    except Exception as e:
        print(f"[DB Reset] Error during cleanup: {str(e)}")
        raise


async def get_user_count():
    """Get count of test users in database (excluding admin)"""
    count = await db.user.count(
        where={"email": {"not": "admin@example.com"}}
    )
    return count


async def get_training_record_count():
    """Get count of training records"""
    count = await db.trainingrecord.count()
    return count


async def get_feedback_count():
    """Get count of feedback entries"""
    count = await db.feedback.count()
    return count


async def verify_database_clean():
    """Verify database is in clean state for testing"""
    users = await get_user_count()
    records = await get_training_record_count()
    feedbacks = await get_feedback_count()
    
    is_clean = users == 0 and records == 0 and feedbacks == 0
    
    print(f"\n[DB Verify] Users: {users}, TrainingRecords: {records}, Feedbacks: {feedbacks}")
    print(f"[DB Verify] Database clean: {is_clean}\n")
    
    return is_clean
