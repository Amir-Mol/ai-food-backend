"""
Pytest configuration and global fixtures for Phase 5 testing.
Sets up mocking, database, and async support.
"""

import pytest
import asyncio
import sys
import os
from unittest.mock import patch, AsyncMock

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db
from tests.mock_llm import (
    mock_get_recipe_suggestion,
    mock_summarize_feedback_history,
    MockAzureOpenAI
)
from tests.utils.database_reset import (
    reset_test_database,
    verify_database_clean
)
from tests.fixtures import (
    create_test_user,
    get_test_user,
    generate_test_token,
    TEST_USER_PROFILES
)


# ==================== PYTEST CONFIGURATION ====================

def pytest_configure(config):
    """Called before test collection begins"""
    print("\n" + "="*60)
    print("PHASE 5: BACKEND TESTING")
    print("="*60)
    print("Initializing test environment...")
    print("- Mock LLM enabled")
    print("- Database auto-reset between tests")
    print("- Async support enabled")
    print("="*60 + "\n")


# ==================== EVENT LOOP ====================

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ==================== DATABASE FIXTURES ====================

@pytest.fixture(scope="function")
async def clean_database():
    """
    Reset database before each test.
    Ensures clean state for test isolation.
    """
    # Connect to Prisma
    await db.connect()
    
    print("\n[Setup] Resetting database...")
    await reset_test_database()
    is_clean = await verify_database_clean()
    if not is_clean:
        raise RuntimeError("Database not properly cleaned!")
    yield
    # Cleanup after test
    await reset_test_database()
    # Disconnect from Prisma
    await db.disconnect()


# ==================== LLM MOCKING ====================

@pytest.fixture(scope="function")
def mock_llm():
    """
    Mock the Azure OpenAI LLM calls by replacing the client initialization.
    This ensures all chat.completions.create calls use the mock instead of real API.
    """
    # Clear the LRU cache so get_azure_openai_client() creates a new instance
    import ai_service_client
    ai_service_client.get_azure_openai_client.cache_clear()
    
    # Now patch to return mock client
    mock_client = MockAzureOpenAI()
    
    with patch(
        "ai_service_client.get_azure_openai_client",
        return_value=mock_client
    ):
        print("[Setup] LLM mocking enabled (Azure client intercepted)")
        yield {
            "client": mock_client,
            "recipe_suggestion": mock_get_recipe_suggestion,
            "summarize_feedback": mock_summarize_feedback_history
        }


# ==================== TEST USER FIXTURES ====================

@pytest.fixture(scope="function")
async def test_user_a(clean_database):
    """Create and return test user A"""
    user = await create_test_user("user_a")
    print(f"[Fixture] Test user A created: {user.email}")
    return user


@pytest.fixture(scope="function")
async def test_user_b(clean_database):
    """Create and return test user B"""
    user = await create_test_user("user_b")
    print(f"[Fixture] Test user B created: {user.email}")
    return user


# ==================== AUTHENTICATION FIXTURES ====================

@pytest.fixture(scope="function")
async def auth_token_a(test_user_a):
    """Generate auth token for test user A"""
    token = generate_test_token(test_user_a.id)
    print(f"[Fixture] Auth token generated for user A")
    return token


@pytest.fixture(scope="function")
async def auth_token_b(test_user_b):
    """Generate auth token for test user B"""
    token = generate_test_token(test_user_b.id)
    print(f"[Fixture] Auth token generated for user B")
    return token


# ==================== COMBINED FIXTURES ====================

@pytest.fixture(scope="function")
async def test_user_with_token(clean_database):
    """
    Create test user with auth token.
    Useful for simple tests that need both.
    """
    user = await create_test_user("user_a")
    token = generate_test_token(user.id)
    print(f"[Fixture] User + token ready: {user.email}")
    return {"user": user, "token": token}


# ==================== AUTO-USE FIXTURES ====================

@pytest.fixture(autouse=True)
def test_header(request):
    """Print test header before each test"""
    print(f"\n{'='*60}")
    print(f"TEST: {request.node.name}")
    print(f"{'='*60}")
    yield
    print(f"{'='*60}\n")
