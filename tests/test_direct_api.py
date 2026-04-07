"""
Direct API test - Tests the exact data flow without needing login.
Uses an existing verified user's ID from the backend logs.
"""

import requests
import json
import time
from typing import Dict, Any, Optional

# Rahti backend URL
BASE_URL = "https://backend-app-nutrirecom.2.rahtiapp.fi"

# This is the user from your backend logs who has recommendations
EXISTING_USER_ID = "a9963b7b-aa47-4e3d-8b39-9ba9343a0172"
EXISTING_USER_EMAIL = "s3pcnv1byh@lnovic.com"

# You need to provide the access token for this user
# Option 1: Get it from your app's SharedPreferences or local login
# Option 2: Set it below if you know it
ACCESS_TOKEN = None  # SET THIS TO THE TOKEN IF YOU KNOW IT

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def log_section(title: str):
    print(f"\n{Colors.HEADER}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{title.center(80)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*80}{Colors.ENDC}\n")

def log_success(msg: str):
    print(f"{Colors.GREEN}✅ {msg}{Colors.ENDC}")

def log_error(msg: str):
    print(f"{Colors.RED}❌ {msg}{Colors.ENDC}")

def log_info(msg: str):
    print(f"{Colors.BLUE}ℹ️  {msg}{Colors.ENDC}")

def log_warning(msg: str):
    print(f"{Colors.YELLOW}⚠️  {msg}{Colors.ENDC}")

def log_request(method: str, endpoint: str, status: int):
    color = Colors.GREEN if status == 200 else Colors.RED if status >= 400 else Colors.YELLOW
    print(f"{color}[{method}] {endpoint} → {status}{Colors.ENDC}")

def print_json(data: Any, indent: int = 2):
    """Pretty print JSON data"""
    print(json.dumps(data, indent=indent, default=str))

def test_get_recommendations(token: str):
    """Test GET /api/recommendations/ endpoint"""
    log_section("TEST 1: GET /api/recommendations/")
    
    url = f"{BASE_URL}/api/recommendations/"
    headers = {"Authorization": f"Bearer {token}"}
    
    log_info("Fetching recommendations...")
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        log_request("GET", "/api/recommendations/", response.status_code)
        
        if response.status_code == 200:
            data = response.json()
            log_success("Recommendations fetched!")
            
            print(f"{Colors.CYAN}Response JSON:{Colors.ENDC}")
            print_json(data)
            
            # Analyze the recommendations
            recs = data.get("recommendations", [])
            if recs:
                print(f"\n{Colors.BOLD}Analysis of First Recommendation:{Colors.ENDC}")
                rec = recs[0]
                
                print(f"  recipeId: {Colors.BOLD}{rec.get('recipeId')}{Colors.ENDC}")
                print(f"  name: {rec.get('name')}")
                print(f"  healthScore: {rec.get('healthScore')}")
                print(f"  imageUrl: {rec.get('imageUrl', 'MISSING')}")
                print(f"  ingredients: {len(rec.get('ingredients', []))} items" if rec.get('ingredients') else f"  ingredients: MISSING")
                
                # Check for the unknown_id problem
                if rec.get('recipeId') == 'unknown_id':
                    log_error("PROBLEM FOUND: recipeId is 'unknown_id'!")
                    log_warning("This explains feedback submission failures")
                    return False
                else:
                    log_success("recipeId looks good!")
                    return True
            else:
                log_warning("No recommendations in response")
                return False
        else:
            log_error(f"Failed: {response.text}")
            return False
    except Exception as e:
        log_error(f"Request failed: {str(e)}")
        return False

def test_check_training_records(token: str):
    """Check if training records exist for this user"""
    log_section("TEST 2: Check Training Records in Database")
    
    log_info(f"User ID: {EXISTING_USER_ID}")
    log_info("This requires direct database access (not available via API)")
    log_warning("Check backend logs instead for training record creation messages")
    
    return True

def test_submit_feedback(token: str, recipe_id: str):
    """Test feedback submission"""
    log_section(f"TEST 3: Submit Feedback for Recipe '{recipe_id}'")
    
    url = f"{BASE_URL}/api/recommendations/{recipe_id}/feedback"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "liked": True,
        "healthinessScore": 4,
        "tastinessScore": 4,
        "intentToTryScore": 5
    }
    
    log_info(f"Submitting feedback to: {url}")
    print_json(payload)
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        log_request("POST", f"/api/recommendations/{recipe_id}/feedback", response.status_code)
        
        if response.status_code == 200:
            log_success("Feedback submitted successfully!")
            print_json(response.json())
            return True
        elif response.status_code == 404:
            log_error(f"404: Training record not found for recipe '{recipe_id}'")
            log_error("DIAGNOSIS: Training records missing from database!")
            log_error("This means the async generation didn't create them")
            return False
        else:
            log_error(f"Failed: {response.text}")
            return False
    except Exception as e:
        log_error(f"Request failed: {str(e)}")
        return False

def main():
    print(f"\n{Colors.BOLD}DIRECT API TEST{Colors.ENDC}")
    print(f"{Colors.BOLD}Backend URL: {BASE_URL}{Colors.ENDC}")
    print(f"{Colors.BOLD}User ID: {EXISTING_USER_ID}{Colors.ENDC}\n")
    
    if not ACCESS_TOKEN:
        log_error("No access token provided!")
        log_info("\nTO RUN THIS TEST:")
        log_info("1. Open your Flutter app and login with: {EXISTING_USER_EMAIL}")
        log_info("2. In VS Code terminal, run: flutter logs")
        log_info("3. Find the access token being sent in requests (Bearer token)")
        log_info("4. Copy that token and set ACCESS_TOKEN = 'your_token_here' in this script")
        log_info("5. Run the test again")
        return
    
    # Run tests
    if not test_get_recommendations(ACCESS_TOKEN):
        log_error("GET recommendations test failed!")
        return
    
    # Get the recipe ID from recommendations
    url = f"{BASE_URL}/api/recommendations/"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    response = requests.get(url, headers=headers, timeout=10)
    
    if response.status_code == 200:
        data = response.json()
        recs = data.get("recommendations", [])
        if recs:
            recipe_id = recs[0].get("recipeId")
            
            test_check_training_records(ACCESS_TOKEN)
            test_submit_feedback(ACCESS_TOKEN, recipe_id)
    
    log_section("NEXT STEPS")
    print(f"""
{Colors.CYAN}To fully diagnose the issue:{Colors.ENDC}

1. {Colors.BOLD}Check Backend Logs{Colors.ENDC}
   Look for messages like:
   - "Creating TRAINING RECORDS..."
   - "Training record creation error..."
   
   Compare them with what you see when:
   - Fresh user does onboarding (async path)
   - User calls POST /api/generate-recommendations (manual path)

2. {Colors.BOLD}Check if Code Deployed{Colors.ENDC}
   Our fix should create these log messages:
   - "Data enrichment complete..."
   - "Creating 5 training records..."
   - "Created X/5 training records..."
   
   If you don't see these, the new code didn't deploy!

3. {Colors.BOLD}Check for Errors{Colors.ENDC}
   Look for any Python tracebacks in the backend logs
   Our code might have a syntax error or runtime issue
""")

if __name__ == "__main__":
    main()
