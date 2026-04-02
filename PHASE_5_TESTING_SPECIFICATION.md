# Phase 5: Comprehensive Backend Testing Without Frontend

## Overview
Test all Version2 features by simulating complete dataflows using:
- Direct API calls (Postman/Python)
- Database queries (psql/pgAdmin)
- Log file inspection
- Mock LLM responses

**Goal**: Verify backend works "flawlessly" before frontend integration.

---

## Test Infrastructure Required

### 1. Test Database Setup
- [ ] Ensure test database populated with sample recipes
- [ ] Clear User/TrainingRecord tables before each test scenario
- [ ] Script to reset database to clean state

### 2. Mock Azure OpenAI (or use test environment)
- [ ] Create mock LLM client that returns deterministic responses
- [ ] OR: Use Azure OpenAI with test deployment
- [ ] Avoid production usage during testing

### 3. Test Data Fixtures
- [ ] Create 5 test users with different profiles
- [ ] Create 20 sample feedback items (varied actions/ratings)
- [ ] Create expected recommendation outputs (for comparison)

### 4. Test Client Setup
Use Postman, cURL, or Python requests library to make API calls:
```bash
# Example: Create test user
curl -X POST http://localhost:8000/api/user \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "name": "Test User"}'

# Example: Submit feedback
curl -X POST http://localhost:8000/api/{recommendation_id}/feedback \
  -H "Authorization: Bearer {token}" \
  -d '{"action": "liked", "rating": 5}'
```

---

## SCENARIO A: Post-Onboarding Auto-Generation

**Goal**: Verify fresh recommendations auto-generate after onboarding.

**Steps**:

1. **Setup**
   - [ ] Create new test user in database
   - [ ] Verify initial state:
     ```sql
     SELECT recommendationGenerationStatus, recommendations, nextAllowedGenerationAt
     FROM users WHERE id = '{test_user_id}';
     -- Expected: status="idle", recommendations=null, nextAllowedGenerationAt=null
     ```

2. **Trigger Onboarding Completion**
   - [ ] POST `/api/user/complete-onboarding`
   - [ ] Expected response: `{"status": "generation_started"}`
   - [ ] Check logs: Should see `[{user_id}] Status: generating`

3. **Monitor Status (Poll 3 Seconds)**
   - [ ] GET `/api/recommendation-status` (repeat every 3 seconds)
   - [ ] Expected sequence:
     ```
     Poll 1: {"status": "generating", "recommendationsReadyAt": null}
     Poll 2: {"status": "generating", ...}
     Poll 3: {"status": "ready", "recommendationsReadyAt": "2026-03-30T10:15:30Z"}
     ```

4. **Verify Database Updates**
   - [ ] After status="ready", check database:
     ```sql
     SELECT 
       recommendationGenerationStatus,
       recommendations,
       recommendationsReadyAt,
       nextAllowedGenerationAt
     FROM users WHERE id = '{test_user_id}';
     ```
   - [ ] Expected:
     ```
     status: "ready"
     recommendations: [5 recipe JSON objects with explanations]
     recommendationsReadyAt: Recent timestamp
     nextAllowedGenerationAt: Now + 1 hour
     ```

5. **Verify Recommendations Quality**
   - [ ] Check recommendations JSON structure:
     ```json
     {
       "recipeId": "...",
       "title": "...",
       "explanation": "...",
       ...
     }
     ```
   - [ ] Verify count: exactly 5 recipes
   - [ ] Verify all recipes match filters (dietary restrictions, allergies, etc.)

6. **Check Logs for Complete Pipeline**
   - [ ] Search logs for `[{user_id}]`:
     ```
     [test_user_1] Status: generating
     [test_user_1] Generated 100 consideration set
     [test_user_1] LLM returned 5 recommendations
     [test_user_1] Saved recommendations to database
     [test_user_1] Status: ready
     ```

7. **Verify Timer Gate Active**
   - [ ] Try POST `/api/recommendations` (new request)
   - [ ] Expected: HTTP 429 with message
     ```json
     {
       "detail": "Please wait 59 minute(s) before requesting new recommendations."
     }
     ```

---

## SCENARIO B: 5-Feedback Summarization Cycle

**Goal**: Verify feedback accumulation triggers summarization + new generation.

**Steps**:

1. **Setup**
   - [ ] Create test user with completed onboarding
   - [ ] Verify initial recommendations exist
   - [ ] Initial state:
     ```sql
     SELECT feedbackSummaryForEmbedding, feedbackSummaryLastUpdatedAt FROM users;
     -- Expected: both null
     ```

2. **Submit 4 Feedbacks** (not 5 yet—no summarization)
   - [ ] POST `/api/{recommendation_id}/feedback` (4 times)
   - [ ] Each POST response: `{"status": "feedback_received"}`
   - [ ] Check logs: **NO** summarization should start
   - [ ] Database state: All 4 TrainingRecords saved
     ```sql
     SELECT COUNT(*) FROM trainingrecords WHERE userId = '{test_user_id}';
     -- Expected: 4
     ```

3. **Submit 5th Feedback** (triggers summarization)
   - [ ] POST `/api/{recommendation_id}/feedback` (5th time)
   - [ ] Expected response: `{"status": "feedback_received"}`
   - [ ] Immediately check status:
     ```
     GET /api/recommendation-status
     -- Expected: status="summarizing" (if async task started quickly)
     ```
   - [ ] Check logs for: `[{user_id}] Summarizing 5 feedbacks`

4. **Monitor Summarization** (Poll every 2 seconds)
   - [ ] GET `/api/recommendation-status` repeatedly
   - [ ] Expected sequence:
     ```
     Poll 1: {"status": "summarizing"}
     Poll 2: {"status": "summarizing"}
     Poll 3: {"status": "generating"} ← After summarization completes
     Poll 4: {"status": "ready"} ← After new recommendations generated
     ```

5. **Verify Feedback Summaries Created**
   - [ ] Check database:
     ```sql
     SELECT 
       feedbackSummaryForEmbedding,
       feedbackSummaryForLLM,
       feedbackSummaryLastUpdatedAt
     FROM users WHERE id = '{test_user_id}';
     ```
   - [ ] Expected:
     ```
     feedbackSummaryForEmbedding: "1-2 sentences, ~100 chars"
     feedbackSummaryForLLM: "3-5 sentences, ~300-400 chars"
     feedbackSummaryLastUpdatedAt: Recent timestamp
     ```

6. **Verify NEW Recommendations Generated**
   - [ ] Check if recommendations changed:
     ```sql
     SELECT recommendations FROM users WHERE id = '{test_user_id}';
     -- Should be DIFFERENT from original (if feedback influenced preferences)
     ```
   - [ ] Verify Stage 1 included feedback summary:
     - Check logs: `[{user_id}] Generating stage 1 with feedback_summary`
     - New consideration set should reflect learned preferences

7. **Verify New Timer Gate Set**
   - [ ] Check nextAllowedGenerationAt updated:
     ```sql
     SELECT nextAllowedGenerationAt FROM users WHERE id = '{test_user_id}';
     -- Should be roughly 1 hour from now
     ```

8. **Check Logs for Complete Pipeline**
   - [ ] Verify entire sequence logged:
     ```
     [test_user_1] Summarizing 5 feedbacks
     [test_user_1] LLM summary: embedding_summary + llm_summary
     [test_user_1] Summaries updated
     [test_user_1] Status: generating
     [test_user_1] Generate stage 1 with feedback_summary
     [test_user_1] Generated 100 consideration set
     [test_user_1] LLM returned 5 recommendations
     [test_user_1] Status: ready
     ```

---

## SCENARIO C: Timer Gate Blocking

**Goal**: Verify 1-hour timer prevents duplicate requests.

**Steps**:

1. **Setup**
   - [ ] Use user from Scenario B (has active timer)
   - [ ] Verify nextAllowedGenerationAt is in the future:
     ```sql
     SELECT nextAllowedGenerationAt FROM users WHERE id = '{test_user_id}';
     -- Expected: timestamp > NOW()
     ```

2. **Attempt Manual Recommendation Request**
   - [ ] POST `/api/recommendations` (requesting new recommendations)
   - [ ] Expected: HTTP 429 (Too Many Requests)
   - [ ] Response body:
     ```json
     {
       "detail": "Please wait 47 minute(s) before requesting new recommendations."
     }
     ```
   - [ ] Verify wait time is reasonable (between 0-60 minutes)

3. **Verify Timer Message Accuracy**
   - [ ] Make 3 requests 10 seconds apart
   - [ ] Wait times should decrease by ~10 seconds each:
     ```
     Request 1: "Please wait 45 minutes..."
     Request 2: "Please wait 44 minutes..." (approximately)
     Request 3: "Please wait 44 minutes..."
     ```

4. **Verify Logging**
   - [ ] Logs should show request was blocked:
     ```
     [test_user_1] Timer gate: nextAllowedGenerationAt in future, blocking request
     ```

---

## SCENARIO D: Fresh Stage 1 Discovery

**Goal**: Verify each request generates new Stage 1 (not cached).

**Steps**:

1. **Setup**
   - [ ] Create two test users A and B
   - [ ] Reset timer gate: Set `nextAllowedGenerationAt = NULL` for both
   - [ ] Generate initial recommendations for User A
   - [ ] Record Stage 1 consideration set:
     ```sql
     -- This requires logging or saving Stage 1 results
     -- Check logs for: "Generated 100 consideration set"
     ```

2. **Make First Recommendation Request (User A)**
   - [ ] POST `/api/recommendations` → Get 5 recommendations
   - [ ] Record recipe IDs in recommendations set #1:
     ```
     Set #1: [recipe_123, recipe_456, recipe_789, recipe_321, recipe_654]
     ```
   - [ ] Check logs for Stage 1 generation (not cache hit)

3. **Modify User A's Profile Slightly** (to influence Stage 1)
   - [ ] Add liked ingredient: "garlic"
   - [ ] POST `/api/user/profile` with update
   - [ ] Reset timer: `nextAllowedGenerationAt = NULL`

4. **Make Second Recommendation Request (User A)**
   - [ ] POST `/api/recommendations` → Get 5 new recommendations
   - [ ] Record recipe IDs in recommendations set #2:
     ```
     Set #2: [recipe_111, recipe_222, recipe_333, recipe_456, recipe_999]
     ```
   - [ ] **VERIFY**: Sets should be DIFFERENT (at least 3-4 recipes different)
   - [ ] Check logs: Should see "Generated 100 consideration set" again (fresh generation, not cache)

5. **Compare Stage 1 Results**
   - [ ] Log should show different Stage 1 outputs due to profile change:
     ```
     Request 1 logs: "Generated 100 consideration set [IDs...]"
     Request 2 logs: "Generated 100 consideration set [different IDs...]"
     ```

6. **Expected Result**
   - [ ] Second request includes new preferences
   - [ ] At least 2-3 recipes differ from first request
   - [ ] No cache hit occurred (verified via logs)

---

## SCENARIO E: Concurrent Feedback Handling

**Goal**: Verify system handles concurrent feedback safely.

**Steps**:

1. **Setup**
   - [ ] Create test user
   - [ ] Reset timer and summary fields
   - [ ] Prepare 5 feedback requests

2. **Submit 5 Feedbacks Rapidly** (within 1 second)
   - [ ] Use threading/concurrent requests:
     ```python
     import concurrent.futures
     
     def submit_feedback(rec_id):
         response = requests.post(
             f"http://localhost:8000/api/{rec_id}/feedback",
             json={"action": "liked", "rating": 5},
             headers={"Authorization": f"Bearer {token}"}
         )
         return response.status_code
     
     with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
         results = executor.map(submit_feedback, [rec_1, rec_2, rec_3, rec_4, rec_5])
     ```
   - [ ] Expected: All 5 return 200 OK

3. **Verify Database Consistency**
   - [ ] Check TrainingRecord count:
     ```sql
     SELECT COUNT(*) FROM trainingrecords WHERE userId = '{test_user_id}';
     -- Expected: exactly 5 (no duplicates, no losses)
     ```
   - [ ] Check all 5 records saved correctly:
     ```sql
     SELECT * FROM trainingrecords WHERE userId = '{test_user_id}'
     ORDER BY createdAt;
     -- Expected: 5 distinct records with different timestamps
     ```

4. **Verify Summarization Triggered Once**
   - [ ] Check logs: Should see ONE summarization start, not multiple
     ```
     [test_user_1] Summarizing 5 feedbacks ← Should appear once
     [test_user_1] Summarizing 5 feedbacks ← Should NOT appear again
     ```
   - [ ] Verify no duplicate summarization jobs

5. **Expected Result**
   - [ ] All 5 feedbacks saved
   - [ ] No data corruption
   - [ ] Exactly one summarization job triggered

---

## Database Verification Checklist

After each scenario, verify database integrity:

```sql
-- User fields updated correctly
SELECT 
  id, email,
  recommendationGenerationStatus,
  recommendationsReadyAt,
  nextAllowedGenerationAt,
  feedbackSummaryForEmbedding,
  feedbackSummaryForLLM,
  feedbackSummaryLastUpdatedAt,
  recommendations
FROM users
WHERE id = '{test_user_id}';

-- TrainingRecords created
SELECT 
  id, userId, action, rating, notes, createdAt
FROM trainingrecords
WHERE userId = '{test_user_id}'
ORDER BY createdAt DESC;

-- Recommendations field structure
SELECT recommendations::jsonb FROM users WHERE id = '{test_user_id}';
-- Should return: [{"recipeId": "...", "title": "...", "explanation": "...", ...}, ...]
```

---

## Log Verification Checklist

After each scenario, search logs for:

```
✓ User-scoped logging: [test_user_1]
✓ Step-by-step pipeline: "Generating stage 1" → "LLM returned" → "Status: ready"
✓ Error handling: All exceptions captured with context
✓ Timing info: Performance metrics (Stage 1: X seconds, LLM: Y seconds)
✓ Status transitions: idle → generating/summarizing → ready
✓ Database operations: Update success messages
```

---

## Load Testing (Concurrent Users)

**Goal**: Verify system handles multiple users simultaneously.

**Setup**:
```python
import concurrent.futures
import requests
import time

def user_workflow(user_id, token):
    # 1. Complete onboarding
    requests.post("/api/user/complete-onboarding", 
                  headers={"Authorization": f"Bearer {token}"})
    
    # 2. Poll status until ready
    for _ in range(30):
        response = requests.get("/api/recommendation-status",
                               headers={"Authorization": f"Bearer {token}"})
        if response.json()["status"] == "ready":
            break
        time.sleep(1)
    
    # 3. Submit feedback 5 times
    for i in range(5):
        requests.post(f"/api/recommendation/{i}/feedback",
                     json={"action": "liked", "rating": 5},
                     headers={"Authorization": f"Bearer {token}"})

# Run with 10 concurrent users
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(user_workflow, i, token_i) for i in range(10)]
    results = [f.result() for f in concurrent.futures.as_completed(futures)]
```

**Verify**:
- [ ] All 10 users complete successfully
- [ ] No database corruption
- [ ] All recommendations generated within reasonable time
- [ ] No race conditions or deadlocks

---

## Success Criteria: Phase 5 Complete

✅ All 5 scenarios pass completely
✅ No database inconsistencies
✅ All logs show complete pipelines
✅ Load testing handles 10 concurrent users
✅ Fresh Stage 1 discovery confirmed
✅ Timer gates block correctly
✅ Feedback summarization works with 5+ feedbacks
✅ Async jobs complete and update database
✅ Error cases handled gracefully (fallback to Stage 1 if LLM fails)
✅ All edge cases covered (null summaries, empty feedback, etc.)

---

## Files Needed for Testing

**Create these files**:
- [ ] `tests/test_scenarios.py` - Unit tests for each scenario
- [ ] `tests/fixtures.py` - Test data and user fixtures
- [ ] `tests/conftest.py` - Pytest configuration
- [ ] `TESTING_GUIDE.md` - Manual testing instructions
- [ ] `postman_collection.json` - Postman API collection for manual testing

---

## Timeline

**Phase 5 Testing Timeline**:
- Day 1: Test infrastructure setup (fixtures, database isolation)
- Day 2: Run Scenarios A-C (onboarding, summarization, timer)
- Day 3: Run Scenarios D-E (discovery, concurrency) + load testing
- Day 4: Compile results, fix any issues, document findings
- Day 5: Create PR to main branch with test results

**Total: 5 days for comprehensive backend validation**
