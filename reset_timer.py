"""
Quick script to reset nextAllowedGenerationAt for the current user.
This fixes the issue where old timer values remain in the database
after code deployment with different timer durations.
"""

import asyncio
from prisma import Prisma
import os
from dotenv import load_dotenv

load_dotenv()

async def reset_user_timer():
    """Reset nextAllowedGenerationAt to NULL for the user"""
    db = Prisma()
    await db.connect()
    
    try:
        # First, find all users to see who has the name/email matching
        all_users = await db.user.find_many()
        print(f"Total users in database: {len(all_users)}")
        for u in all_users[:10]:  # Show first 10 users
            print(f"  - ID: {u.id[:8]}..., Email: {u.email}, Name: {u.name}")
        
        # Try to find by email pattern (h8dgkce might be in the email)
        user = None
        for u in all_users:
            if "h8dgkce" in u.email:
                user = u
                break
        
        if not user and all_users:
            # Fall back to most recent user
            user = all_users[-1]
            print(f"\nUsing most recent user...")
        
        if not user:
            print("❌ No users found in database")
            return
        
        print(f"\nFound user: {user.email}")
        print(f"Current nextAllowedGenerationAt: {user.nextAllowedGenerationAt}")
        
        # Reset the timer
        updated_user = await db.user.update(
            where={"id": user.id},
            data={"nextAllowedGenerationAt": None}  # Set to NULL
        )
        
        print(f"✅ Timer reset successfully!")
        print(f"New nextAllowedGenerationAt: {updated_user.nextAllowedGenerationAt}")
        
    finally:
        await db.disconnect()

if __name__ == "__main__":
    asyncio.run(reset_user_timer())
