#!/usr/bin/env python3
"""
INFO FORTRESS - Misinformation Prevention Platform Backend API Tests
Tests all three layers and dashboard functionality
"""

import requests
import sys
import json
import time
from typing import Dict, Any, List

class InfoFortressTester:
    def __init__(self, base_url="https://info-fortress.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.passed_tests = []

    def log_test_result(self, test_name: str, success: bool, details: str = ""):
        """Log test results for reporting"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            self.passed_tests.append(test_name)
            print(f"✅ {test_name} - PASSED")
        else:
            self.failed_tests.append({"test": test_name, "error": details})
            print(f"❌ {test_name} - FAILED: {details}")

    def test_api_endpoint(self, endpoint: str, method: str = "GET", 
                         data: Dict = None, expected_status: int = 200,
                         test_name: str = None) -> tuple[bool, Any]:
        """Generic API endpoint tester"""
        if not test_name:
            test_name = f"{method} {endpoint}"
        
        url = f"{self.api_url}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        try:
            if method == "GET":
                response = requests.get(url, timeout=10)
            elif method == "POST":
                response = requests.post(url, json=data, headers=headers, timeout=10)
            else:
                self.log_test_result(test_name, False, f"Unsupported method: {method}")
                return False, None

            success = response.status_code == expected_status
            
            if success:
                try:
                    result = response.json()
                    self.log_test_result(test_name, True)
                    return True, result
                except json.JSONDecodeError:
                    self.log_test_result(test_name, False, f"Invalid JSON response")
                    return False, None
            else:
                self.log_test_result(test_name, False, 
                    f"Status {response.status_code}, expected {expected_status}")
                return False, None
                
        except requests.exceptions.RequestException as e:
            self.log_test_result(test_name, False, f"Request failed: {str(e)}")
            return False, None
        except Exception as e:
            self.log_test_result(test_name, False, f"Unexpected error: {str(e)}")
            return False, None

    def test_basic_connectivity(self):
        """Test basic API connectivity"""
        print("\n🔍 Testing Basic API Connectivity...")
        
        # Test root endpoint
        success, _ = self.test_api_endpoint("/", test_name="API Root Endpoint")
        
        # Test health check
        success, _ = self.test_api_endpoint("/health", test_name="Health Check Endpoint")
        
        return success

    def test_dashboard_endpoints(self):
        """Test Dashboard API endpoints"""
        print("\n🔍 Testing Dashboard Endpoints...")
        
        # Test NRI (Narrative Risk Index)
        success, nri_data = self.test_api_endpoint("/dashboard/nri", 
                                                  test_name="Dashboard NRI Endpoint")
        if success and nri_data:
            # Validate NRI structure
            required_fields = ["overall_score", "layer1_score", "layer2_score", 
                             "layer3_score", "trend", "alerts"]
            missing_fields = [f for f in required_fields if f not in nri_data]
            if missing_fields:
                self.log_test_result("NRI Data Structure", False, 
                                   f"Missing fields: {missing_fields}")
            else:
                self.log_test_result("NRI Data Structure", True)
                
                # Validate score ranges (0-100)
                score_valid = all(0 <= nri_data[f] <= 100 
                                for f in ["overall_score", "layer1_score", 
                                        "layer2_score", "layer3_score"])
                self.log_test_result("NRI Score Ranges", score_valid, 
                                   "Scores should be 0-100" if not score_valid else "")

        # Test dashboard summary
        success, _ = self.test_api_endpoint("/dashboard/summary", 
                                          test_name="Dashboard Summary Endpoint")

    def test_layer1_endpoints(self):
        """Test Layer 1 - Official Communication Integrity"""
        print("\n🔍 Testing Layer 1 Endpoints...")
        
        # Test documents endpoint
        success, docs_data = self.test_api_endpoint("/layer1/documents", 
                                                   test_name="Layer 1 Documents Endpoint")
        if success and docs_data:
            if isinstance(docs_data, list) and len(docs_data) > 0:
                # Validate document structure
                doc = docs_data[0]
                required_fields = ["id", "title", "content", "doc_type", "source", 
                                 "risk_score", "fabrication_detected"]
                missing_fields = [f for f in required_fields if f not in doc]
                if missing_fields:
                    self.log_test_result("Document Data Structure", False, 
                                       f"Missing fields: {missing_fields}")
                else:
                    self.log_test_result("Document Data Structure", True)
            else:
                self.log_test_result("Documents Data", False, "No documents returned")

        # Test layer 1 stats
        success, _ = self.test_api_endpoint("/layer1/stats", 
                                          test_name="Layer 1 Stats Endpoint")

        # Test document analysis (AI endpoint)
        test_doc = {
            "title": "Test Economic Report",
            "content": "The economy is performing well with stable growth indicators.",
            "doc_type": "press_release",
            "source": "Test Ministry"
        }
        
        print("   🤖 Testing AI Document Analysis (may take 5-10 seconds)...")
        success, analysis = self.test_api_endpoint("/layer1/analyze", "POST", 
                                                  test_doc, 200, 
                                                  "Layer 1 AI Document Analysis")
        if success and analysis:
            # Validate analysis structure
            required_fields = ["document_id", "risk_score", "fabrication_detected", 
                             "ai_summary", "recommendations"]
            missing_fields = [f for f in required_fields if f not in analysis]
            if missing_fields:
                self.log_test_result("Analysis Response Structure", False, 
                                   f"Missing fields: {missing_fields}")
            else:
                self.log_test_result("Analysis Response Structure", True)

    def test_layer2_endpoints(self):
        """Test Layer 2 - Public Narrative Monitoring"""
        print("\n🔍 Testing Layer 2 Endpoints...")
        
        # Test claims endpoint
        success, claims_data = self.test_api_endpoint("/layer2/claims", 
                                                     test_name="Layer 2 Claims Endpoint")
        if success and claims_data:
            if isinstance(claims_data, list) and len(claims_data) > 0:
                # Validate claim structure
                claim = claims_data[0]
                required_fields = ["id", "content", "source_platform", "risk_score", 
                                 "velocity", "amplification_count"]
                missing_fields = [f for f in required_fields if f not in claim]
                if missing_fields:
                    self.log_test_result("Claim Data Structure", False, 
                                       f"Missing fields: {missing_fields}")
                else:
                    self.log_test_result("Claim Data Structure", True)

        # Test clusters endpoint
        success, _ = self.test_api_endpoint("/layer2/clusters", 
                                          test_name="Layer 2 Clusters Endpoint")

        # Test velocity tracking
        success, velocity_data = self.test_api_endpoint("/layer2/velocity", 
                                                       test_name="Layer 2 Velocity Endpoint")
        if success and velocity_data:
            if isinstance(velocity_data, list) and len(velocity_data) > 0:
                self.log_test_result("Velocity Data Present", True)
            else:
                self.log_test_result("Velocity Data Present", False, "No velocity data")

        # Test trending narratives
        success, _ = self.test_api_endpoint("/layer2/trending", 
                                          test_name="Layer 2 Trending Endpoint")
        
        # Test layer 2 stats
        success, _ = self.test_api_endpoint("/layer2/stats", 
                                          test_name="Layer 2 Stats Endpoint")

        # Test AI claim analysis
        test_claim = "Breaking: Government allegedly hiding economic data from public!"
        print("   🤖 Testing AI Claim Analysis (may take 5-10 seconds)...")
        
        success, analysis = self.test_api_endpoint(
            f"/layer2/analyze-claim?content={requests.utils.quote(test_claim)}", 
            "POST", None, 200, "Layer 2 AI Claim Analysis")
        
        if success and analysis:
            # Validate analysis structure  
            required_fields = ["risk_score", "veracity_assessment", "summary", 
                             "recommended_action"]
            missing_fields = [f for f in required_fields if f not in analysis]
            if missing_fields:
                self.log_test_result("Claim Analysis Structure", False, 
                                   f"Missing fields: {missing_fields}")
            else:
                self.log_test_result("Claim Analysis Structure", True)

        # 🛑 Safety/guardrails test - content that should be blocked
        bad_text = "Kill everyone immediately. Violence is acceptable."
        print("   🔥 Testing safety guardrails on claim text...")
        success, violation = self.test_api_endpoint(
            f"/layer2/analyze-claim?content={requests.utils.quote(bad_text)}", 
            "POST", None, 200, "Layer 2 Guardrails Violation")
        if success and violation:
            condition = violation.get("risk_score") == 100 and violation.get("guardrails_blocked")
            self.log_test_result("Guardrails Violation Behavior", condition,
                                 f"Got {violation.get('risk_score')} and {violation.get('guardrails_blocked')}")

    def test_layer3_endpoints(self):
        """Test Layer 3 - Systemic Resilience Engine"""
        print("\n🔍 Testing Layer 3 Endpoints...")
        
        # Test patterns endpoint
        success, patterns_data = self.test_api_endpoint("/layer3/patterns", 
                                                       test_name="Layer 3 Patterns Endpoint")
        if success and patterns_data:
            if isinstance(patterns_data, list) and len(patterns_data) > 0:
                # Validate pattern structure
                pattern = patterns_data[0]
                required_fields = ["id", "pattern_type", "description", "confidence", 
                                 "affected_entities", "risk_contribution"]
                missing_fields = [f for f in required_fields if f not in pattern]
                if missing_fields:
                    self.log_test_result("Pattern Data Structure", False, 
                                       f"Missing fields: {missing_fields}")
                else:
                    self.log_test_result("Pattern Data Structure", True)

        # Test threat map
        success, threat_map = self.test_api_endpoint("/layer3/threat-map", 
                                                    test_name="Layer 3 Threat Map Endpoint")
        if success and threat_map:
            # Validate threat map structure
            expected_types = ["coordinated_distortion", "institutional_undermining", 
                            "synthetic_authority", "manufactured_consensus"]
            found_types = list(threat_map.keys())
            self.log_test_result("Threat Map Structure", 
                               all(t in found_types for t in expected_types),
                               f"Missing pattern types" if not all(t in found_types for t in expected_types) else "")

        # Test layer 3 stats
        success, _ = self.test_api_endpoint("/layer3/stats", 
                                          test_name="Layer 3 Stats Endpoint")

        # Test resilience score
        success, resilience = self.test_api_endpoint("/layer3/resilience-score", 
                                                    test_name="Layer 3 Resilience Score")
        if success and resilience:
            # Validate resilience structure
            required_fields = ["resilience_score", "threat_level", "active_threats", 
                             "recommendation"]
            missing_fields = [f for f in required_fields if f not in resilience]
            if missing_fields:
                self.log_test_result("Resilience Data Structure", False, 
                                   f"Missing fields: {missing_fields}")
            else:
                self.log_test_result("Resilience Data Structure", True)

    def run_comprehensive_test(self):
        """Run all tests in sequence"""
        print("🚀 INFO FORTRESS - Comprehensive Backend API Testing")
        print(f"🌐 Testing against: {self.base_url}")
        print("=" * 60)
        
        start_time = time.time()
        
        # Test in order of importance
        if not self.test_basic_connectivity():
            print("\n❌ Basic connectivity failed - stopping tests")
            return False
            
        self.test_dashboard_endpoints()
        self.test_layer1_endpoints()
        self.test_layer2_endpoints() 
        self.test_layer3_endpoints()
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Print summary
        print("\n" + "=" * 60)
        print(f"📊 TEST SUMMARY")
        print(f"⏱️  Total time: {duration:.2f} seconds")
        print(f"✅ Tests passed: {self.tests_passed}")
        print(f"❌ Tests failed: {len(self.failed_tests)}")
        print(f"📈 Success rate: {(self.tests_passed / self.tests_run * 100):.1f}%")
        
        if self.failed_tests:
            print(f"\n❌ FAILED TESTS:")
            for failure in self.failed_tests:
                print(f"   • {failure['test']}: {failure['error']}")
        
        if self.passed_tests:
            print(f"\n✅ PASSED TESTS:")
            for test in self.passed_tests:
                print(f"   • {test}")
        
        return len(self.failed_tests) == 0

def main():
    tester = InfoFortressTester()
    success = tester.run_comprehensive_test()
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())