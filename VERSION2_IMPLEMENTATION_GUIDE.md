# AI Food Recommendation System - Version2 Implementation Guide

## Executive Summary

**Goal**: Implement feedback-driven recommendation generation with intelligent pre-computation to reduce user wait time and improve LLM discovery effectiveness.

**Current Status**: 
- Main branch: Completed csc-migration (all pending migrations merged)
- Starting point: we will continue to work in csc-migration branch
- Scope: Backend implementation only (5 phases, 2-3 days estimated)

**Key Innovation**: Generate FRESH consideration sets on each request (instead of caching) + iterative feedback summarization + auto-trigger recommendations during idle time.

---

## Part 1: Current Architecture & Problem Analysis

### Current Two-Stage Ranking System

**Stage 1 - Semantic Search** (`backend/recommender/engine.py`):
- Loads pre-computed recipe embeddings (9,995 × 384 NumPy array)
- Creates user document from profile (likes, cuisines, activity level, dietary info)
- Generates user embedding with SentenceTransformer (all-MiniLM-L6-v2)
- Scores all recipes: cosine similarity + hard constraints + soft penalties/bonuses
- Hard constraints: allergies, dietary restrictions, health conditions
- Soft scoring: dislikes penalty (0.3×), likes bonus (1.2×)
- Outputs: Top 100 recipes (CONSIDERATION_SET_SIZE)

**Stage 2 - LLM Reranking** (`backend/api/recipes.py` → `backend/ai_service_client.py`):
- Takes Stage 1 output (100 recipes)
- Sends to Azure OpenAI (GPT-4o) with user profile summary
- LLM returns ranked top 5 with structured explanations
- User receives 5 recipes with personalized reasoning

### The Problem Identified

**Current Limitation**: Consideration sets are CACHED per user in memory (`CONSIDERATION_SET_CACHE` lines 85-89 in recipes.py).

**Impact**:
- User cycles through same 100 recipes across multiple "Find a Meal" requests
- LLM role is limited to REORDERING existing set, not DISCOVERING new recipes
- User reaches end of cached 100 → no new content until cache reset
- LLM's reasoning power undermined: determines which 5 of pre-selected 100, not which 100 should be considered

**Root Cause**: 
- Stages 1 and 2 are only triggered once per user
- Feedback recorded in TrainingRecord but NOT integrated back into user profile
- No mechanism to reflect user preferences evolution over time

---

## Part 2: Version2 Solution Design

### Core Strategy

**Three Pillars**:

1. **Fresh Consideration Set Generation**
   - Remove caching → generate new Stage 1 on each "Find a Meal" request
   - Invalidate cache when user profile changes (feedback summary updates)
   - LLM can now discover from full pool, not fixed 100

2. **Iterative Feedback Summarization**
   - Capture raw feedback in TrainingRecord (unchanged)
   - After every 5 feedbacks OR on demand: LLM synthesizes feedback → summary
   - Two versions of summary:
     - `feedbackSummaryForEmbedding`: 1-2 sentences for Stage 1 semantic search
     - `feedbackSummaryForLLM`: 3-5 sentences detailed for Stage 2 reasoning
   - Each cycle: previous_summary + 5 new feedbacks → LLM updated summary
   - Avoids information loss cascade, reflects preference drift

3. **Auto-Triggered Recommendations**
   - Auto-start generation after onboarding completion
   - Auto-start generation after feedback submission
   - Pre-compute while user sees loading state
   - User never waits for Stage 1 + LLM latency (typically 10+ seconds)
   - 1-hour timer gate prevents request spam, gives system breathing room

### Data Flow - Version2

```
User submits feedback (like/dislike/rating)
    ↓
TrainingRecord created (raw feedback stored)
    ↓
Check: 5 feedbacks accumulated since last summary?
    ├─ YES: Async job summarizes feedback
    │       Takes: previous_summary (or null) + 5 new items
    │       LLM returns: embedding_summary + llm_summary + length
    │       Updates User: feedbackSummaryForEmbedding, feedbackSummaryForLLM
    │       Clears CONSIDERATION_SET_CACHE (if exists in memory)
    │
    └─ NO: Just save feedback, continue
    
    ↓
Async job triggers recommendation generation
    Calls: generate_consideration_set() with NEW feedbackSummaryForEmbedding
    Calls: get_recipe_suggestion() with NEW feedbackSummaryForLLM
    Saves 5 recommended recipes to User recommendations field
    Updates User: recommendationGenerationStatus = "ready"
    
    ↓
Frontend polls GET /api/recommendation-status every 3 seconds
    Receives: {"status": "ready", "nextAllowedGenerationAt": timestamp}
    Auto-navigates to RecommendationResultsScreen
    
    ↓
User views 5 pre-computed recommendations
    No wait time (pre-computed during idle time)
    
    ↓
User submits feedback (cycle repeats)
    Next "Find a Meal" click disabled until nextAllowedGenerationAt expires
```

---

## Part 3: Database Schema Changes

### New User Fields (Prisma Schema)

Add 4 new fields to User model in `backend/prisma/schema.prisma`:

```prisma
// Finalized feedback summaries (updated iteratively after every 5 feedbacks)
feedbackSummaryForEmbedding    String?    // ~100 chars (1-2 sentences)
feedbackSummaryForLLM          String?    // ~400 chars (3-5 sentences)

// Generation status tracking for frontend polling
recommendationGenerationStatus String     @default("idle")  // "idle" | "summarizing" | "generating" | "ready"
recommendationsReadyAt         DateTime?  // When current round of recommendations became available
nextAllowedGenerationAt        DateTime?  // When user can request new recommendations (1-hour gate)
```

### Schema Notes

- **Do NOT modify TrainingRecord**: Raw feedback stays unchanged for ML analysis
- **Field types**: Text (nullable) for summaries, String enum for status, DateTime optional for timestamps
- **Default behavior**: New users have null summaries, "idle" status, null timestamps
- **Migration required**: Create Prisma migration file after schema edit

---

## Part 4: Implementation Phases

### Phase 1: Prisma Schema Migration (1-2 days)
- [ ] Edit `backend/prisma/schema.prisma` - add 4 User fields
- [ ] Create migration: `prisma migrate dev --name add_feedback_summaries_and_generation_status`
- [ ] Test migration on staging database
- [ ] Regenerate Prisma client
- [ ] Commit to csc-migration branch

### Phase 2: Feedback Summarization Service (2-3 days)
- [ ] Create new file: `backend/prompts/feedback_summary_prompt.py` (LLM prompt templates)
- [ ] Add function to `backend/ai_service_client.py`: `summarize_feedback_history()`
- [ ] Create new file: `backend/api/feedback.py` (feedback handling endpoints)
- [ ] Modify `backend/api/recipes.py`: Add cache invalidation logic
- [ ] Add: Background job to await summarization completion
- [ ] Test: Feedback summarization with mock LLM calls

### Phase 3: Auto-Generation System (2-3 days)
- [ ] Create new file: `backend/tasks/recommendation_generator.py` (async generation logic)
- [ ] Create new file: `backend/api/status.py` (status polling endpoint)
- [ ] Modify `backend/api/recipes.py`: Add status endpoint, trigger generation
- [ ] Add: Timer gate enforcement (check nextAllowedGenerationAt)
- [ ] Add: Generation status tracking (idle → summarizing → generating → ready)
- [ ] Test: Auto-trigger after onboarding, after feedback

### Phase 4: Integration & Edge Cases (1 day)
- [ ] Handle null feedback summaries (new users)
- [ ] Handle concurrent feedback submissions
- [ ] Handle generation failures gracefully
- [ ] Add logging for monitoring
- [ ] Database migration rollback procedure

### Phase 5: Testing & Documentation (1-2 days)
- [ ] End-to-end test: onboarding → auto-trigger → recommendations ready
- [ ] Test: Feedback cycle → summarization → new recommendations
- [ ] Test: Timer gate prevents premature requests
- [ ] Test: Fresh Stage 1 discovery (different recipes on successive requests)
- [ ] Load testing: Multiple concurrent users
- [ ] Create PR to main branch

---

## Part 5: Detailed Backend Implementation

### 5.1 File: `backend/prisma/schema.prisma`

**Location**: Lines after existing User fields (around line 27-50)

**Change**: Add these 4 fields to User model:

```prisma
model User {
  // ... existing fields ...
  
  // Version2: Feedback summarization fields
  feedbackSummaryForEmbedding    String?    // 1-2 sentence summary for Stage 1
  feedbackSummaryForLLM          String?    // 3-5 sentence summary for Stage 2
  
  // Version2: Generation status tracking
  recommendationGenerationStatus String     @default("idle")
  recommendationsReadyAt         DateTime?
  nextAllowedGenerationAt        DateTime?
  
  // ... existing relations (TrainingRecord, etc) ...
}
```

**After Edit**:
```bash
cd backend
prisma migrate dev --name add_version2_fields
```

---

### 5.2 File: `backend/ai_service_client.py`

**Current Content**: Handles Azure OpenAI calls for Stage 2 LLM reranking

**Add New Function** (around line 200, after `get_recipe_suggestion`):

```python
def summarize_feedback_history(
    previous_summary: Optional[str],
    new_feedbacks: List[Dict[str, Any]],
    user_preferences: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Uses LLM to synthesize feedback into two complementary summaries:
    1. embedding_summary: 1-2 sentences for Stage 1 semantic search
    2. llm_summary: 3-5 sentences detailed for Stage 2 reasoning
    
    Takes previous summary + 5 new feedback items, iteratively updates.
    
    Args:
        previous_summary: Last computed summary (None if first time)
        new_feedbacks: List of dicts with: {recipe_name, action, rating, notes}
        user_preferences: User profile for context
    
    Returns:
        {
            "embedding_summary": str,  # ~100 chars
            "llm_summary": str,        # ~300-400 chars
            "feedback_count": int
        }
    """
    # Build feedback list for prompt
    feedback_items = "\n".join([
        f"- {fb['recipe_name']}: {fb['action']} (rating: {fb.get('rating', 'N/A')})"
        for fb in new_feedbacks
    ])
    
    prompt = f"""Analyze this user's food preferences evolution.

Previous Summary: {previous_summary or 'None (first time)'}

New Feedback (5 recent items):
{feedback_items}

User Background:
- Likes: {', '.join(user_preferences.get('likedIngredients', []))}
- Cuisines: {', '.join(user_preferences.get('favoriteCuisines', []))}
- Activity Level: {user_preferences.get('activityLevel')}

CRITICAL: Generate exactly 2 summaries:

1. EMBEDDING_SUMMARY (max 2 sentences, ~100 chars for vector search):
   Compress into terse preference keywords. Must be scannable.

2. LLM_SUMMARY (3-5 sentences, ~300-400 chars for reasoning):
   Include specific recipe types, cuisines, ingredients they like/dislike.
   Reference preference evolution if evident from feedback.

Return as JSON:
{{
    "embedding_summary": "...",
    "llm_summary": "..."
}}
"""
    
    response = client.beta.messages.create(
        model=deployment_name,
        max_tokens=800,
        temperature=0.3,  # More deterministic for summarization
        messages=[{"role": "user", "content": prompt}]
    )
    
    # Parse JSON response
    response_text = response.content[0].text
    result = json.loads(response_text)
    
    return {
        "embedding_summary": result["embedding_summary"],
        "llm_summary": result["llm_summary"],
        "feedback_count": len(new_feedbacks)
    }
```

**Notes**:
- Temperature 0.3 (lower than Stage 2's 0.7) for consistent summarization
- Prompt emphasizes two different objectives for each summary
- Length guidance helps avoid token bloat
- Returns structured dict for database updates

---

### 5.3 File: `backend/api/recipes.py`

**Current Content**: Main recommendation endpoint, handles Stage 1 + Stage 2 pipeline

**Modify Function**: `generate_recommendations()` (POST /api/recommendations)

**Current Lines ~80-120** (rough):
- Line 85-89: CONSIDERATION_SET_CACHE check
- Line 84: Calls generate_consideration_set()
- Line 120: Calls get_recipe_suggestion()

**Changes Needed**:

1. **Remove caching check** (lines 85-89):
   - Delete the CONSIDERATION_SET_CACHE if-check logic
   - Always call generate_consideration_set() fresh

2. **Add feedbackSummaryForEmbedding to user_document**:
   OLD (in engine.py `_create_user_document`):
   ```python
   document = (
       f"A user who likes {likes}. "
       f"They enjoy {cuisines} cuisines. "
       ...
   )
   ```
   
   NEW: Pass feedbackSummaryForEmbedding as parameter
   ```python
   def _create_user_document(user_profile: Dict[str, Any], feedback_summary: Optional[str] = None) -> str:
       """Creates a single text string from a user's profile for embedding."""
       likes = ', '.join(user_profile.get('likedIngredients', []))
       cuisines = ', '.join(user_profile.get('favoriteCuisines', []))
       
       dietary_profile = user_profile.get('dietaryProfile') or {}
       dietary_restrictions = dietary_profile.get('dietaryRestrictions') or {}
       diet_info = ', '.join(dietary_restrictions.get('selected', []))

       document = (
           f"A user who likes {likes}. "
           f"They enjoy {cuisines} cuisines. "
           f"Their dietary profile includes: {diet_info}. "
           f"They have an activity level of {user_profile.get('activityLevel', 'unknown')}."
       )
       
       # Add feedback summary if available (evolved preferences)
       if feedback_summary:
           document += f" Recent preferences: {feedback_summary}"
       
       return document
   ```

3. **Update generate_recommendations() call**:
   ```python
   user_profile = ... # existing code
   feedback_summary = user.feedbackSummaryForEmbedding  # NEW
   
   consideration_set = generate_consideration_set(
       user_profile=user_profile,
       recipes_df=RECIPES_DF,
       recipe_embeddings=RECIPE_EMBEDDINGS
   )
   # Note: Still called fresh each time (no caching)
   ```

4. **Pass feedbackSummaryForLLM to LLM**:
   ```python
   user_profile_for_llm = {
       **user_profile,
       "feedbackSummary": user.feedbackSummaryForLLM  # NEW
   }
   
   recommendations = get_recipe_suggestion(
       consideration_set=consideration_set,
       user_profile=user_profile_for_llm
   )
   ```

**Important**: Do NOT delete CONSIDERATION_SET_CACHE variable yet—might have other references. Just stop using it.

---

### 5.4 New File: `backend/tasks/recommendation_generator.py`

**Purpose**: Async background job for generating and pre-computing recommendations

**Content**:

```python
"""
Background task for auto-generating recommendations.
Triggered after onboarding completion and after feedback cycles.
Runs asynchronously to avoid blocking user requests.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional
import logging

from database import db  # Prisma client
from recommender.engine import generate_consideration_set, RECIPES_DF, RECIPE_EMBEDDINGS
from ai_service_client import get_recipe_suggestion
from config import CONSIDERATION_SET_SIZE

logger = logging.getLogger(__name__)

async def generate_and_save_recommendations(user_id: str, feedback_summarization_in_progress: bool = False):
    """
    Generate personalized recommendations and save to user's profile.
    
    Flow:
    1. Update status to "generating"
    2. Generate fresh consideration set (Stage 1)
    3. Call LLM for top 5 (Stage 2)
    4. Save recommendations to user.recommendations
    5. Update status to "ready"
    6. Set nextAllowedGenerationAt = now + 1 hour
    
    Args:
        user_id: User ID to generate recommendations for
        feedback_summarization_in_progress: If True, wait for summarization to complete
    """
    try:
        # Fetch user from database
        user = await db.user.find_unique(where={"id": user_id})
        if not user:
            logger.error(f"User {user_id} not found")
            return
        
        # Update status
        await db.user.update(
            where={"id": user_id},
            data={"recommendationGenerationStatus": "generating"}
        )
        logger.info(f"[{user_id}] Status: generating")
        
        # Step 1: Generate consideration set (Stage 1)
        # Convert user profile fields to dict for engine
        user_profile = {
            "likedIngredients": user.likedIngredients or [],
            "dislikedIngredients": user.dislikedIngredients or [],
            "favoriteCuisines": user.favoriteCuisines or [],
            "activityLevel": user.activityLevel or "moderately active",
            "weight": user.weight,
            "height": user.height,
            "age": user.age,
            "gender": user.gender,
            "foodAllergies": user.foodAllergies or {},
            "dietaryProfile": user.dietaryProfile or {},
        }
        
        consideration_set = generate_consideration_set(
            user_profile=user_profile,
            recipes_df=RECIPES_DF,
            recipe_embeddings=RECIPE_EMBEDDINGS,
            consideration_set_size=CONSIDERATION_SET_SIZE
        )
        logger.info(f"[{user_id}] Generated {len(consideration_set)} consideration set")
        
        # Step 2: Call LLM for top 5 (Stage 2)
        user_profile_for_llm = {
            **user_profile,
            "feedbackSummary": user.feedbackSummaryForLLM or "No feedback history yet"
        }
        
        recommendations = get_recipe_suggestion(
            consideration_set=consideration_set,
            user_profile=user_profile_for_llm
        )
        logger.info(f"[{user_id}] LLM returned {len(recommendations)} recommendations")
        
        # Step 3: Save to database
        next_allowed = datetime.utcnow() + timedelta(hours=1)
        
        await db.user.update(
            where={"id": user_id},
            data={
                "recommendations": recommendations,  # Store as JSON
                "recommendationsReadyAt": datetime.utcnow(),
                "nextAllowedGenerationAt": next_allowed,
                "recommendationGenerationStatus": "ready"
            }
        )
        logger.info(f"[{user_id}] Status: ready. Next allowed: {next_allowed}")
        
    except Exception as e:
        logger.error(f"[{user_id}] Generation failed: {str(e)}")
        await db.user.update(
            where={"id": user_id},
            data={"recommendationGenerationStatus": "idle"}  # Reset on error
        )


async def trigger_feedback_summarization(user_id: str, new_feedbacks: list):
    """
    Async trigger for feedback summarization pipeline.
    
    Checks if 5 feedbacks accumulated, calls LLM summarization, invalidates cache.
    
    Args:
        user_id: User ID
        new_feedbacks: List of recent feedback dicts
    """
    from ai_service_client import summarize_feedback_history
    
    try:
        user = await db.user.find_unique(where={"id": user_id})
        if not user:
            return
        
        logger.info(f"[{user_id}] Summarizing {len(new_feedbacks)} feedbacks")
        
        # Update status to "summarizing"
        await db.user.update(
            where={"id": user_id},
            data={"recommendationGenerationStatus": "summarizing"}
        )
        
        # Call LLM summarization
        user_profile = {
            "likedIngredients": user.likedIngredients or [],
            "favoriteCuisines": user.favoriteCuisines or [],
            "activityLevel": user.activityLevel or "moderately active",
        }
        
        summary_result = summarize_feedback_history(
            previous_summary=user.feedbackSummaryForEmbedding,
            new_feedbacks=new_feedbacks,
            user_preferences=user_profile
        )
        
        # Update user with new summaries
        await db.user.update(
            where={"id": user_id},
            data={
                "feedbackSummaryForEmbedding": summary_result["embedding_summary"],
                "feedbackSummaryForLLM": summary_result["llm_summary"],
            }
        )
        logger.info(f"[{user_id}] Summaries updated")
        
        # Auto-trigger new recommendation generation
        await generate_and_save_recommendations(user_id)
        
    except Exception as e:
        logger.error(f"[{user_id}] Summarization failed: {str(e)}")
        await db.user.update(
            where={"id": user_id},
            data={"recommendationGenerationStatus": "idle"}
        )
```

**Notes**:
- Use `async` / `await` pattern (depends on your async DB client setup)
- Log everything for monitoring/debugging
- Error handling gracefully resets status to "idle"
- Called from API endpoints (see next section)

---

### 5.5 New File: `backend/api/status.py`

**Purpose**: Endpoint for frontend status polling

**Content**:

```python
"""
Recommendation generation status endpoint.
Frontend polls this every 3 seconds to know when recommendations are ready.
"""

from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime

from database import get_current_user

router = APIRouter(prefix="/api", tags=["status"])

@router.get("/recommendation-status")
async def get_recommendation_status(user = Depends(get_current_user)):
    """
    Returns current generation status and timing info.
    
    Response:
    {
        "status": "idle" | "summarizing" | "generating" | "ready",
        "recommendationsReadyAt": ISO datetime or null,
        "nextAllowedGenerationAt": ISO datetime or null
    }
    
    Frontend uses:
    - status == "ready": Auto-navigate to results screen
    - status in ["summarizing", "generating"]: Show loading spinner
    - nextAllowedGenerationAt: Compare to now() for countdown timer
    """
    return {
        "status": user.recommendationGenerationStatus,
        "recommendationsReadyAt": user.recommendationsReadyAt,
        "nextAllowedGenerationAt": user.nextAllowedGenerationAt
    }
```

**Integration**: Import and include router in main `main.py`:
```python
from api import status
app.include_router(status.router)
```

---

### 5.6 Modify File: `backend/api/recipes.py`

**Location in generate_recommendations()** (existing POST /api/recommendations endpoint)

**Add this logic after successful Stage 1 + Stage 2 completion**:

```python
# After saving TrainingRecord (existing line ~176-187)

# NEW: Check if we should trigger feedback summarization + auto-generation
feedback_count = await db.trainingRecord.count(
    where={
        "userId": user.id,
        "createdAt": {"gte": user.feedbackSummaryForEmbedding_updatedAt}  # or similar
    }
)

if feedback_count >= 5:
    # Queue async job: summarize feedback, then generate recommendations
    from tasks.recommendation_generator import trigger_feedback_summarization
    
    recent_feedbacks = await db.trainingRecord.find_many(
        where={"userId": user.id},
        order_by={"createdAt": "desc"},
        take=5
    )
    
    # Convert to format for summarization
    feedback_dicts = [
        {
            "recipe_name": fb.recommendation.title,
            "action": fb.action,  # "liked", "disliked", "rated"
            "rating": fb.rating,
            "notes": fb.notes
        }
        for fb in recent_feedbacks
    ]
    
    # Trigger async (don't wait)
    asyncio.create_task(
        trigger_feedback_summarization(user.id, feedback_dicts)
    )

# Also: Check timer gate before calling generate_recommendations in first place
if user.nextAllowedGenerationAt and user.nextAllowedGenerationAt > datetime.utcnow():
    raise HTTPException(
        status_code=429,
        detail=f"Please wait {(user.nextAllowedGenerationAt - datetime.utcnow()).total_seconds() // 60:.0f} minutes"
    )
```

---

### 5.7 New Endpoint: Trigger Auto-Start After Onboarding

**Add to main API** (could be in `api/users.py` or `api/onboarding.py`):

```python
@router.post("/api/complete-onboarding")
async def complete_onboarding(user = Depends(get_current_user)):
    """
    Called by frontend after final onboarding screen.
    Triggers auto-generation of initial recommendations.
    """
    from tasks.recommendation_generator import generate_and_save_recommendations
    import asyncio
    
    # Trigger async generation (don't wait)
    asyncio.create_task(
        generate_and_save_recommendations(user.id)
    )
    
    return {"status": "generation_started"}
```

---

## Part 6: Code Files to Read & Inspect

**Critical Files to Review** (in order):

1. `backend/prisma/schema.prisma` (lines 1-50)
   - Understand User model structure
   - Identify where to add 4 new fields

2. `backend/config.py`
   - Check CONSIDERATION_SET_SIZE value
   - Check LLM configuration (deployment name, model)

3. `backend/recommender/engine.py`
   - Lines 24-35: `_create_user_document()` - where to add feedback_summary parameter
   - Lines 75-171: `_calculate_score()` - understand scoring logic
   - Lines 214-269: `generate_consideration_set()` - main orchestrator
   - Verify no caching logic here (it's in recipes.py)

4. `backend/api/recipes.py`
   - Lines 1-30: Imports and setup
   - Lines 70-90: CONSIDERATION_SET_CACHE reference
   - Lines 85-120: `generate_recommendations()` endpoint - where to remove caching
   - Lines 176-187: TrainingRecord save logic
   - Identify where to add timer gate check

5. `backend/ai_service_client.py`
   - Lines 1-50: Imports, Azure OpenAI client setup
   - Lines 80-130: `get_recipe_suggestion()` - existing Stage 2 call
   - Line 200+: Where to add `summarize_feedback_history()` function

6. `backend/database.py`
   - Understand Prisma client setup
   - How to make async queries

7. `backend/main.py`
   - How routers are imported/included
   - Where to add new status router

---

## Part 7: Testing Checklist

### Unit Tests

- [ ] `summarize_feedback_history()` with null previous summary
- [ ] `summarize_feedback_history()` with existing summary
- [ ] `generate_and_save_recommendations()` happy path
- [ ] Timer gate blocks request when nextAllowedGenerationAt in future
- [ ] Fresh consideration set differs from previous request

### Integration Tests

- [ ] Complete flow: User onboarding → auto-trigger → status polling → ready
- [ ] Feedback cycle: Submit feedback → 5 feedbacks → summarization → auto-generation
- [ ] Database: User fields updated correctly after summarization
- [ ] LLM calls: Verify prompt structure and response parsing

### Manual Testing

- [ ] Create test user, complete onboarding, verify recommendations generated
- [ ] Poll status endpoint during generation
- [ ] Submit 5 feedbacks, verify summarization triggers
- [ ] Next "Find a Meal" click shows timer countdown (frontend)
- [ ] Fresh Stage 1 on subsequent requests (different recipes)

---

## Part 8: Important Constraints & Notes

### Code Stability

**CRITICAL**: You mentioned "The app and the backend are working flawlessly!" 

**Implications**:
1. Existing endpoints remain unchanged in behavior (synchronous get)
2. CONSIDERATION_SET_CACHE reference: Only STOP using it, don't delete yet
3. All changes are ADDITIVE (new files, new fields)
4. Backward compatibility: Existing code paths unchanged

### Migration Strategy

1. **Before starting**:
   - Ensure main branch has all csc-migration completed
   - we will continue to modify csc-migration branch

2. **Phase 1 (Prisma)**:
   - Edit schema.prisma
   - Run migration (creates migration file automatically)
   - Test migration reversibility: `prisma migrate resolve --rolled-back`

3. **Phases 2-5**:
   - Each phase is isolated (can rollback easily)
   - Commit frequently with descriptive messages
   - Tag checkpoints: `git tag phase2-complete`

4. **Final**:
   - Create PR to main when all phases complete
   - Code review focusing on:
     - No breaking changes to existing endpoints
     - Async error handling
     - Edge cases (null summaries, concurrent feedback)
     - Logging for observability

### Async Considerations

- Backend likely uses FastAPI (async-capable)
- Database client should support async (Prisma does)
- Use `asyncio.create_task()` for fire-and-forget jobs
- Never block request thread on LLM calls

### Feedback Summarization Timing

- Triggered after 5 feedbacks OR manually by user request
- Should be optimized for length (LLM tendency: output bloat)
- Current settings: Temperature 0.3 (low randomness), max_tokens 800
- Monitor: How long does summarization take?

---

## Part 9: GitHub Workflow

```bash
# 1. Ensure main is up-to-date with csc-migration merged
git checkout main
git pull origin main

# 2. 

# 3. Phase 1: Schema
# - Edit schema.prisma
# - prisma migrate dev --name add_version2_fields
git add prisma/
git commit -m "Phase 1: Add feedback summary and generation status fields"
git tag phase1-schema-complete

# 4. Phase 2: Feedback Summarization
# - New files: prompts/feedback_summary_prompt.py, api/feedback.py
# - Modify: ai_service_client.py, recipes.py
# - Add: summarize_feedback_history() function
git add backend/
git commit -m "Phase 2: Implement feedback summarization service"
git tag phase2-summarization-complete

# 5. Phase 3: Auto-Generation
# - New files: tasks/recommendation_generator.py, api/status.py
# - Add: endpoints and async jobs
git add backend/
git commit -m "Phase 3: Implement auto-generation and status polling"
git tag phase3-autogen-complete

# 6. Phase 4: Integration
# - Tie everything together
# - Add edge case handling
git add backend/
git commit -m "Phase 4: Integration and edge case handling"
git tag phase4-integration-complete

# 7. Phase 5: Testing & Documentation
# - Add tests
# - Update README
git add backend/tests/ backend/README.md
git commit -m "Phase 5: Testing and documentation"


```

---

## Part 10: Success Criteria

✅ **Backend Implementation Complete When**:

1. Prisma migration runs without errors
2. `summarize_feedback_history()` returns valid 2-summary JSON
3. `/api/recommendation-status` returns correct status and timestamps
4. Fresh Stage 1 generation differs between successive calls
5. Timer gate blocks requests within 1-hour window
6. Feedback summarization triggers after 5 feedbacks
7. Auto-generation at onboarding and post-feedback completes
8. All edge cases handled (null summaries, concurrent requests, LLM failures)
9. Logging sufficient for production monitoring
10. No breaking changes to existing endpoints
11. PR approved and merged to main

---

## Quick Reference: File Checklist

```
Backend Changes Needed:
├── MODIFIED:
│   ├── prisma/schema.prisma (+4 fields)
│   ├── ai_service_client.py (+1 function)
│   ├── recommender/engine.py (modify _create_user_document signature)
│   └── api/recipes.py (remove caching, add timer gate, add async triggers)
│
├── NEW:
│   ├── tasks/recommendation_generator.py (async jobs)
│   ├── api/status.py (status endpoint)
│   └── prompts/feedback_summary_prompt.py (LLM prompts)
│
└── INTEGRATION:
    └── main.py (include new routers)
```

---

## Next Steps for New Chat

1. **Start by reading**: 
   - `backend/prisma/schema.prisma` (full file)
   - `backend/config.py` (identify key values)
   - `backend/ai_service_client.py` (understand Azure OpenAI setup)

2. **Then begin Phase 1**: Prisma schema migration

3. **Reference this document** for implementation details, code snippets, and file locations

4. **Ask clarifications if**: Any assumptions about async patterns, database client, or LLM response format differ from actual codebase

---

**Document Created**: March 30, 2026  
**Purpose**: Backend Version2 Implementation Guide  
**Status**: Ready for new chat startup
