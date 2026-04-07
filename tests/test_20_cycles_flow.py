"""
Comprehensive frontend-accurate flow test with 20 cycles.

This test replicates EXACTLY what the Flutter app does:
1. Login
2. Trigger onboarding (async generation)
3. Poll for status
4. Fetch recommendations
5. Submit feedback for EACH recommendation with proper survey fields:
   - liked: boolean
   - healthinessScore: 1-5
   - tastinessScore: 1-5
   - intentToTryScore: 1-5
6. Repeat steps 2-5 up to 20 times (until data runs out or max cycles reached)

This validates that all data sent/received matches frontend expectations.
"""

import requests
import json
import time
import sys
from datetime import datetime
from typing import Dict, Any, Optional, List

# Rahti backend URL
BASE_URL = "https://backend-app-nutrirecom.2.rahtiapp.fi"

# Test user credentials (real verified account)
TEST_EMAIL = "s3pcnv1byh@lnovic.com"
TEST_PASSWORD = "StrongPass1234"

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
    print(f"\n{Colors.HEADER}{'='*100}{Colors.ENDC}")
    print(f"{Colors.HEADER}{title.center(100)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*100}{Colors.ENDC}\n")

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

class ValidationResult:
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.successes: List[str] = []
    
    def add_error(self, msg: str):
        self.errors.append(msg)
        log_error(msg)
    
    def add_warning(self, msg: str):
        self.warnings.append(msg)
        log_warning(msg)
    
    def add_success(self, msg: str):
        self.successes.append(msg)
        log_success(msg)
    
    def is_valid(self) -> bool:
        return len(self.errors) == 0

class FrontendFlowSimulator:
    def __init__(self):
        self.token: Optional[str] = None
        self.recommendations: List[Dict[str, Any]] = []
        self.total_feedbacks_submitted = 0
        self.current_cycle = 0
        self.max_cycles = 20
        self.validation = ValidationResult()
        
    def login(self) -> bool:
        """Log in user"""
        log_section("AUTHENTICATION: Login")
        url = f"{BASE_URL}/api/auth/login"
        
        payload = {
            "username": TEST_EMAIL,
            "password": TEST_PASSWORD
        }
        
        log_info(f"Logging in: {TEST_EMAIL}")
        
        try:
            response = requests.post(url, data=payload, timeout=10)
            log_request("POST", "/api/auth/login", response.status_code)
            
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
                log_success(f"Login successful. Token obtained.")
                return True
            else:
                log_error(f"Login failed: {response.text}")
                self.validation.add_error(f"Login failed with status {response.status_code}")
                return False
        except Exception as e:
            log_error(f"Request failed: {str(e)}")
            self.validation.add_error(f"Login request error: {str(e)}")
            return False
    
    def trigger_generation(self) -> bool:
        """Trigger async recommendation generation (completeOnboarding)"""
        log_info(f"\n{'='*80}\nCYCLE {self.current_cycle + 1}/{self.max_cycles}\n{'='*80}")
        
        url = f"{BASE_URL}/api/user/complete-onboarding"
        headers = {"Authorization": f"Bearer {self.token}"}
        
        log_info("Triggering async recommendation generation...")
        
        try:
            response = requests.post(url, headers=headers, timeout=10)
            log_request("POST", "/api/user/complete-onboarding", response.status_code)
            
            if response.status_code == 200:
                log_success("Generation triggered")
                return True
            else:
                log_error(f"Generation trigger failed: {response.text}")
                self.validation.add_error(f"Generation trigger failed: {response.status_code}")
                return False
        except Exception as e:
            log_error(f"Request failed: {str(e)}")
            return False
    
    def poll_status(self, max_wait: int = 90) -> bool:
        """Poll recommendation status until ready"""
        log_info("Polling for recommendation status...")
        url = f"{BASE_URL}/api/recommendation-status"
        headers = {"Authorization": f"Bearer {self.token}"}
        
        start_time = time.time()
        elapsed = 0
        poll_count = 0
        
        while elapsed < max_wait:
            poll_count += 1
            log_info(f"[Poll #{poll_count}] Status... (elapsed: {elapsed:.1f}s)")
            
            try:
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    status = data.get("status")
                    
                    if status == "ready":
                        log_success(f"Recommendations ready after {elapsed:.1f}s")
                        return True
                    else:
                        log_info(f"  Still generating...")
                        time.sleep(2)
                else:
                    log_error(f"Status check failed: {response.text}")
                    return False
            except Exception as e:
                log_error(f"Request failed: {str(e)}")
                time.sleep(2)
            
            elapsed = time.time() - start_time
        
        log_error(f"Timeout: Recommendations not ready after {max_wait}s")
        return False
    
    def validate_recommendation(self, rec: Dict[str, Any]) -> bool:
        """Validate a recommendation matches frontend expectations"""
        issues = []
        
        # Required fields
        if not rec.get('recipeId'):
            issues.append(f"Missing or invalid recipeId: {rec.get('recipeId')}")
        
        if rec.get('recipeId') == 'unknown_id':
            issues.append(f"CRITICAL: recipeId is 'unknown_id' (will break feedback submission)")
        
        if not rec.get('name'):
            issues.append("Missing name")
        
        if not rec.get('explanation'):
            issues.append("Missing explanation")
        
        if not rec.get('imageUrl'):
            issues.append("Missing imageUrl")
        
        if 'healthScore' not in rec or rec.get('healthScore') is None:
            issues.append("Missing healthScore")
        
        if not rec.get('ingredients') or not isinstance(rec.get('ingredients'), list):
            issues.append(f"Missing or invalid ingredients: {rec.get('ingredients')}")
        
        if not rec.get('recipeUrl'):
            issues.append("Missing recipeUrl")
        
        if not rec.get('nutritionalInfo'):
            issues.append("Missing nutritionalInfo")
        else:
            nut = rec.get('nutritionalInfo')
            required_nut_fields = ['calories', 'protein', 'carbs', 'fat', 'sugars', 'sodium']
            for field in required_nut_fields:
                if field not in nut:
                    issues.append(f"Missing nutritionalInfo.{field}")
        
        return len(issues) == 0, issues
    
    def fetch_recommendations(self) -> bool:
        """Fetch recommendations"""
        log_info("Fetching recommendations...")
        url = f"{BASE_URL}/api/recommendations/"
        headers = {"Authorization": f"Bearer {self.token}"}
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            log_request("GET", "/api/recommendations/", response.status_code)
            
            if response.status_code == 200:
                data = response.json()
                self.recommendations = data.get("recommendations", [])
                
                log_success(f"Fetched {len(self.recommendations)} recommendations")
                
                # Validate each recommendation
                for idx, rec in enumerate(self.recommendations, 1):
                    is_valid, issues = self.validate_recommendation(rec)
                    if is_valid:
                        log_success(f"  Rec #{idx}: {rec.get('name')} (ID: {rec.get('recipeId')}) ✓")
                    else:
                        log_warning(f"  Rec #{idx}: {rec.get('name')} - Issues found:")
                        for issue in issues:
                            log_warning(f"    - {issue}")
                            self.validation.add_warning(f"Rec #{idx}: {issue}")
                
                return True
            else:
                log_error(f"Fetch failed: {response.text}")
                self.validation.add_error(f"Fetch failed: {response.status_code}")
                return False
        except Exception as e:
            log_error(f"Request failed: {str(e)}")
            return False
    
    def submit_feedback_for_recommendation(self, rec: Dict[str, Any]) -> bool:
        """Submit feedback for a single recommendation (survey completion)"""
        recipe_id = rec.get('recipeId')
        recipe_name = rec.get('name', 'Unknown')
        
        # Simulate user survey responses (vary based on healthScore)
        health_score = rec.get('healthScore', 5)
        liked = health_score >= 6  # Like if healthScore is high
        healthiness_score = min(5, max(1, int(health_score)))
        tastiness_score = min(5, (int(health_score) + 2) % 5 + 1)  # Vary it
        intent_score = min(5, (int(health_score) + 1) % 5 + 1)  # Vary it
        
        url = f"{BASE_URL}/api/recommendations/{recipe_id}/feedback"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
        # CRITICAL: This is the exact payload structure the Flutter app sends
        payload = {
            "liked": liked,
            "healthinessScore": healthiness_score,
            "tastinessScore": tastiness_score,
            "intentToTryScore": intent_score,
        }
        
        log_info(f"Submitting feedback for: {recipe_name} (ID: {recipe_id})")
        log_info(f"  Survey responses: liked={liked}, health={healthiness_score}, taste={tastiness_score}, intent={intent_score}")
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            log_request("POST", f"/api/recommendations/{recipe_id}/feedback", response.status_code)
            
            if response.status_code == 200:
                log_success(f"Feedback submitted successfully")
                self.total_feedbacks_submitted += 1
                
                # Validate response
                try:
                    resp_data = response.json()
                    if 'nextAllowedGenerationAt' in resp_data:
                        log_info(f"  Next generation allowed at: {resp_data['nextAllowedGenerationAt']}")
                except:
                    pass
                
                return True
            elif response.status_code == 404:
                log_error(f"404: Training record not found for recipe {recipe_id}")
                log_error(f"  Response: {response.text}")
                self.validation.add_error(f"Training record missing for {recipe_id}")
                return False
            else:
                log_error(f"Feedback submission failed: {response.text}")
                self.validation.add_error(f"Feedback submission failed: {response.status_code}")
                return False
        except Exception as e:
            log_error(f"Request failed: {str(e)}")
            self.validation.add_error(f"Feedback request error: {str(e)}")
            return False
    
    def run_cycle(self) -> bool:
        """Run one complete cycle: trigger → poll → fetch → submit feedback for all"""
        self.current_cycle += 1
        
        # Step 1: Trigger generation
        if not self.trigger_generation():
            return False
        
        time.sleep(1)
        
        # Step 2: Poll for status
        if not self.poll_status():
            log_warning(f"Skipping cycle {self.current_cycle}: status polling failed")
            return False
        
        time.sleep(1)
        
        # Step 3: Fetch recommendations
        if not self.fetch_recommendations():
            log_warning(f"Skipping cycle {self.current_cycle}: fetch failed")
            return False
        
        if not self.recommendations:
            log_warning(f"No recommendations returned in cycle {self.current_cycle}")
            return False
        
        time.sleep(1)
        
        # Step 4: Submit feedback for EACH recommendation (survey completion for each)
        log_section(f"CYCLE {self.current_cycle}: SUBMITTING FEEDBACK ({len(self.recommendations)} items)")
        
        successful_feedbacks = 0
        for idx, rec in enumerate(self.recommendations, 1):
            if self.submit_feedback_for_recommendation(rec):
                successful_feedbacks += 1
            time.sleep(0.5)
        
        log_info(f"\nCycle {self.current_cycle} complete: {successful_feedbacks}/{len(self.recommendations)} feedbacks accepted")
        
        return successful_feedbacks > 0
    
    def run_all_cycles(self):
        """Run all cycles"""
        log_section("COMPREHENSIVE 20-CYCLE FRONTEND FLOW TEST")
        print(f"{Colors.BOLD}Backend: {BASE_URL}{Colors.ENDC}")
        print(f"{Colors.BOLD}User: {TEST_EMAIL}{Colors.ENDC}")
        print(f"{Colors.BOLD}Max Cycles: {self.max_cycles}{Colors.ENDC}\n")
        
        # Login
        if not self.login():
            log_error("Login failed. Exiting.")
            return
        
        time.sleep(1)
        
        # Run cycles
        successful_cycles = 0
        for cycle_num in range(self.max_cycles):
            if not self.run_cycle():
                log_warning(f"Cycle {cycle_num + 1} failed or returned no recommendations")
                if cycle_num >= 2:  # Allow up to 2 failures before giving up
                    break
            else:
                successful_cycles += 1
            
            time.sleep(2)
        
        # Final report
        self._print_final_report(successful_cycles)
    
    def _print_final_report(self, successful_cycles: int):
        """Print comprehensive final report"""
        log_section("TEST COMPLETION REPORT")
        
        print(f"\n{Colors.BOLD}CYCLE SUMMARY:{Colors.ENDC}")
        print(f"  Cycles Completed: {self.current_cycle}/{self.max_cycles}")
        print(f"  Successful Cycles: {successful_cycles}")
        print(f"  Failed Cycles: {self.current_cycle - successful_cycles}")
        
        print(f"\n{Colors.BOLD}FEEDBACK SUMMARY:{Colors.ENDC}")
        print(f"  Total Feedbacks Submitted: {self.total_feedbacks_submitted}")
        
        print(f"\n{Colors.BOLD}DATA VALIDATION SUMMARY:{Colors.ENDC}")
        print(f"  Validation Successes: {len(self.validation.successes)}")
        print(f"  Validation Warnings: {len(self.validation.warnings)}")
        print(f"  Validation Errors: {len(self.validation.errors)}")
        
        if self.validation.errors:
            print(f"\n{Colors.RED}ERRORS FOUND:{Colors.ENDC}")
            for i, error in enumerate(self.validation.errors, 1):
                print(f"  {i}. {error}")
        
        if self.validation.warnings:
            print(f"\n{Colors.YELLOW}WARNINGS:{Colors.ENDC}")
            for i, warning in enumerate(self.validation.warnings[:5], 1):  # Show first 5
                print(f"  {i}. {warning}")
            if len(self.validation.warnings) > 5:
                print(f"  ... and {len(self.validation.warnings) - 5} more warnings")
        
        print(f"\n{Colors.BOLD}OVERALL STATUS:{Colors.ENDC}")
        if self.validation.is_valid():
            log_success("✓ ALL TESTS PASSED - Frontend-Backend data integration is working correctly!")
        else:
            log_error(f"✗ {len(self.validation.errors)} critical error(s) found")
            log_warning(f"✓ {len(self.validation.warnings)} warning(s) to review")

def main():
    simulator = FrontendFlowSimulator()
    simulator.run_all_cycles()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Test interrupted by user{Colors.ENDC}")
        sys.exit(0)
