"""
Comprehensive test to simulate the complete frontend flow:
1. Register new user
2. Log in
3. Complete onboarding
4. Poll for recommendation status
5. Fetch recommendations
6. Submit feedback

This helps identify data flow issues between frontend and Rahti backend.
"""

import requests
import json
import time
import sys
from datetime import datetime
from typing import Dict, Any, Optional

# Rahti backend URL (same as frontend config)
BASE_URL = "https://backend-app-nutrirecom.2.rahtiapp.fi"

# Test user credentials - USING VERIFIED TEST ACCOUNT
TEST_EMAIL = "s3pcnv1byh@lnovic.com"
TEST_PASSWORD = "StrongPass1234"
TEST_USERNAME = "test_user"  # Not used since we're using existing account

# Skip registration since this user already exists and is verified
SKIP_REGISTRATION = True

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

class FrontendSimulator:
    def __init__(self):
        self.token: Optional[str] = None
        self.user_id: Optional[str] = None
        self.recommendations: list = []
        
    def register(self) -> bool:
        """Register new user"""
        log_section("STEP 1: Register New User")
        url = f"{BASE_URL}/api/auth/register"
        payload = {
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "username": TEST_USERNAME
        }
        
        log_info(f"Registering user: {TEST_USERNAME} ({TEST_EMAIL})")
        print_json(payload)
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            log_request("POST", "/api/auth/register", response.status_code)
            
            if response.status_code == 200:
                log_success(f"User registered successfully")
                return True
            else:
                log_error(f"Registration failed: {response.text}")
                return False
        except requests.exceptions.RequestException as e:
            log_error(f"Request failed: {str(e)}")
            return False
    
    def verify_email(self) -> bool:
        """Verify email (auto-verify for testing)"""
        log_section("STEP 1.5: Auto-Verify Email")
        
        # For testing, we'll try to login first, and if it says email not verified,
        # we'll use a verification code from the email (in production this would be sent via email)
        log_info("Attempting to get verification code...")
        
        # In a real test, you'd extract the code from the email
        # For now, we'll assume auto-verification is enabled in dev mode
        log_warning("Note: Email verification requires extracting code from verification email")
        log_info("Proceeding with login - if backend requires verification, it will fail")
        
        return True
    
    def login(self) -> bool:
        """Log in user"""
        log_section("STEP 2: Login")
        url = f"{BASE_URL}/api/auth/login"
        
        # OAuth2PasswordRequestForm expects form data (not JSON)
        # username field is actually the email
        payload = {
            "username": TEST_EMAIL,  # Actually the email!
            "password": TEST_PASSWORD
        }
        
        log_info(f"Logging in: {TEST_EMAIL} (using form data)")
        
        try:
            # Use data= instead of json= for form encoding
            response = requests.post(url, data=payload, timeout=10)
            log_request("POST", "/api/auth/login", response.status_code)
            
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
                log_success(f"Login successful. Token: {self.token[:20]}...")
                print_json(data)
                return True
            elif response.status_code == 403:
                error_msg = response.json().get("detail", "Unknown error")
                if "verify" in error_msg.lower():
                    log_error(f"Login failed: Email not verified")
                    log_warning("The test user needs email verification before login")
                    log_info("In production, you would click the verification link in the email")
                    log_info("\nTO FIX: Use an existing verified test account")
                    log_info("Modify TEST_EMAIL and TEST_PASSWORD in the script to use a verified account")
                    return False
                else:
                    log_error(f"Login failed: {error_msg}")
                    return False
            else:
                log_error(f"Login failed: {response.text}")
                return False
        except requests.exceptions.RequestException as e:
            log_error(f"Request failed: {str(e)}")
            return False
    
    def complete_onboarding(self) -> bool:
        """Complete onboarding to trigger recommendation generation"""
        log_section("STEP 3: Complete Onboarding & Trigger Recommendation Generation")
        url = f"{BASE_URL}/api/user/complete-onboarding"
        
        headers = {"Authorization": f"Bearer {self.token}"}
        
        log_info("Sending complete-onboarding request...")
        log_info("This should trigger async recommendation generation")
        
        try:
            response = requests.post(url, headers=headers, timeout=10)
            log_request("POST", "/api/user/complete-onboarding", response.status_code)
            
            if response.status_code == 200:
                data = response.json()
                log_success("Onboarding completed, async generation triggered")
                print_json(data)
                return True
            else:
                log_error(f"Onboarding completion failed: {response.text}")
                return False
        except requests.exceptions.RequestException as e:
            log_error(f"Request failed: {str(e)}")
            return False
    
    def poll_status(self, max_wait: int = 60) -> bool:
        """Poll recommendation status until ready"""
        log_section("STEP 4: Poll Recommendation Status")
        url = f"{BASE_URL}/api/recommendation-status"
        headers = {"Authorization": f"Bearer {self.token}"}
        
        start_time = time.time()
        elapsed = 0
        poll_count = 0
        
        while elapsed < max_wait:
            poll_count += 1
            log_info(f"[Poll #{poll_count}] Checking status... (elapsed: {elapsed:.1f}s)")
            
            try:
                response = requests.get(url, headers=headers, timeout=10)
                log_request("GET", "/api/recommendation-status", response.status_code)
                
                if response.status_code == 200:
                    data = response.json()
                    status = data.get("status")
                    print(f"  Status: {status}")
                    
                    if status == "ready":
                        log_success(f"Recommendations ready after {elapsed:.1f}s!")
                        print_json(data)
                        return True
                    else:
                        log_info(f"Still generating... ({data.get('message', 'no message')})")
                        time.sleep(2)
                else:
                    log_error(f"Status check failed: {response.text}")
                    return False
            except requests.exceptions.RequestException as e:
                log_error(f"Request failed: {str(e)}")
                time.sleep(2)
            
            elapsed = time.time() - start_time
        
        log_error(f"Timeout: Recommendations not ready after {max_wait}s")
        return False
    
    def fetch_recommendations(self) -> bool:
        """Fetch recommendations using GET endpoint"""
        log_section("STEP 5: Fetch Recommendations (GET /api/recommendations/)")
        url = f"{BASE_URL}/api/recommendations/"
        headers = {"Authorization": f"Bearer {self.token}"}
        
        log_info("Fetching pre-generated recommendations...")
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            log_request("GET", "/api/recommendations/", response.status_code)
            
            if response.status_code == 200:
                data = response.json()
                log_success(f"Recommendations fetched!")
                print(f"{Colors.CYAN}Raw JSON Response:{Colors.ENDC}")
                print_json(data)
                
                # Extract and analyze recommendations
                recs = data.get("recommendations", [])
                log_info(f"\nFound {len(recs)} recommendations")
                
                if recs:
                    log_section("ANALYSIS: Extracted Recommendation Fields")
                    for idx, rec in enumerate(recs):
                        print(f"\n  Recommendation #{idx + 1}:")
                        print(f"    recipeId: {Colors.BOLD}{rec.get('recipeId')}{Colors.ENDC}")
                        print(f"    name: {rec.get('name')}")
                        print(f"    healthScore: {rec.get('healthScore')}")
                        print(f"    imageUrl: {rec.get('imageUrl', 'MISSING')}")
                        print(f"    ingredients: {len(rec.get('ingredients', []))} items")
                        print(f"    recipeUrl: {rec.get('recipeUrl', 'MISSING')}")
                        
                        # Check for missing fields
                        if not rec.get('imageUrl'):
                            log_warning(f"     imageUrl is missing!")
                        if 'healthScore' not in rec:
                            log_warning(f"     healthScore is missing!")
                        if not rec.get('ingredients'):
                            log_warning(f"     ingredients is missing!")
                
                self.recommendations = recs
                return True
            else:
                log_error(f"Fetch failed: {response.text}")
                return False
        except requests.exceptions.RequestException as e:
            log_error(f"Request failed: {str(e)}")
            return False
    
    def submit_feedback(self) -> bool:
        """Submit feedback for first recommendation"""
        if not self.recommendations:
            log_error("No recommendations available to submit feedback for")
            return False
        
        log_section("STEP 6: Submit Feedback for First Recommendation")
        
        rec = self.recommendations[0]
        recipe_id = rec.get("recipeId")
        
        log_info(f"Selected recommendation: {rec.get('name')}")
        log_info(f"Recipe ID: {Colors.BOLD}{recipe_id}{Colors.ENDC}")
        
        if recipe_id == "unknown_id":
            log_error("⚠️  PROBLEM DETECTED: recipeId is 'unknown_id'!")
            log_warning("This explains why feedback submission fails")
            log_warning("Backend cannot find training record for 'unknown_id'")
        
        url = f"{BASE_URL}/api/recommendations/{recipe_id}/feedback"
        headers = {
            "Authorization": f"Bearer {self.token}",
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
                log_error(f"404: Training record not found for recipe {recipe_id}")
                log_warning("DIAGNOSIS: Training records were not created during onboarding!")
                print(f"Response: {response.text}")
                return False
            else:
                log_error(f"Feedback submission failed: {response.text}")
                return False
        except requests.exceptions.RequestException as e:
            log_error(f"Request failed: {str(e)}")
            return False

def main():
    print(f"\n{Colors.BOLD}FRONTEND-BACKEND FLOW TEST{Colors.ENDC}")
    print(f"{Colors.BOLD}Backend URL: {BASE_URL}{Colors.ENDC}")
    print(f"{Colors.BOLD}Using verified test account: {TEST_EMAIL}{Colors.ENDC}\n")
    
    simulator = FrontendSimulator()
    
    # Run the flow
    if not SKIP_REGISTRATION:
        if not simulator.register():
            log_error("Registration failed. Exiting.")
            return
        
        input(f"\n{Colors.BLUE}Press Enter to continue...{Colors.ENDC}")
    else:
        log_section("STEP 1: Login with Existing Verified Account")
        log_success(f"Skipping registration - using existing account: {TEST_EMAIL}")
    
    if not simulator.login():
        log_error("Login failed. Exiting.")
        return
    
    input(f"\n{Colors.BLUE}Press Enter to continue...{Colors.ENDC}")
    
    if not simulator.complete_onboarding():
        log_error("Onboarding failed. Exiting.")
        return
    
    input(f"\n{Colors.BLUE}Press Enter to start polling (this will take ~20-30 seconds)...{Colors.ENDC}")
    
    if not simulator.poll_status(max_wait=90):
        log_error("Status polling failed. Exiting.")
        return
    
    input(f"\n{Colors.BLUE}Press Enter to fetch recommendations...{Colors.ENDC}")
    
    if not simulator.fetch_recommendations():
        log_error("Fetching recommendations failed. Exiting.")
        return
    
    input(f"\n{Colors.BLUE}Press Enter to submit feedback...{Colors.ENDC}")
    
    simulator.submit_feedback()
    
    log_section("TEST COMPLETE")
    print(f"{Colors.CYAN}Check the backend logs to see what happened during this flow{Colors.ENDC}\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Test interrupted by user{Colors.ENDC}")
        sys.exit(0)
