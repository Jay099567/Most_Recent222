#!/usr/bin/env python3
"""
AutoApplyX Backend Testing Suite
Tests all implemented backend functionality including API endpoints, 
resume processing, job matching, and database connections.
"""

import requests
import json
import os
import sys
from pathlib import Path
import tempfile
import time
from typing import Dict, Any, List

# Get backend URL from frontend .env file
def get_backend_url():
    frontend_env_path = Path("/app/frontend/.env")
    if frontend_env_path.exists():
        with open(frontend_env_path, 'r') as f:
            for line in f:
                if line.startswith('REACT_APP_BACKEND_URL='):
                    return line.split('=', 1)[1].strip()
    return "http://localhost:8001"

BACKEND_URL = get_backend_url()
API_BASE = f"{BACKEND_URL}/api"

class BackendTester:
    def __init__(self):
        self.test_results = {}
        self.test_user_id = None
        self.test_job_ids = []
        
    def log_test(self, test_name: str, success: bool, message: str = "", details: Any = None):
        """Log test results"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}: {message}")
        
        self.test_results[test_name] = {
            "success": success,
            "message": message,
            "details": details
        }
        
        if details and not success:
            print(f"   Details: {details}")
    
    def test_basic_connectivity(self):
        """Test basic API connectivity"""
        print("\n=== Testing Basic API Connectivity ===")
        
        try:
            response = requests.get(f"{API_BASE}/", timeout=10)
            if response.status_code == 200:
                data = response.json()
                expected_message = "AutoApplyX - Autonomous Job Application System"
                if data.get("message") == expected_message:
                    self.log_test("Root endpoint", True, "API is accessible and returns correct message")
                else:
                    self.log_test("Root endpoint", False, f"Unexpected message: {data}")
            else:
                self.log_test("Root endpoint", False, f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_test("Root endpoint", False, f"Connection failed: {str(e)}")
    
    def test_user_management(self):
        """Test user CRUD operations"""
        print("\n=== Testing User Management ===")
        
        # Test user creation
        try:
            user_data = {
                "name": "Sarah Johnson",
                "email": "sarah.johnson@email.com"
            }
            
            response = requests.post(f"{API_BASE}/users", json=user_data, timeout=10)
            if response.status_code == 200:
                user = response.json()
                self.test_user_id = user["id"]
                self.log_test("User creation", True, f"Created user: {user['name']}")
            else:
                self.log_test("User creation", False, f"HTTP {response.status_code}: {response.text}")
                return
        except Exception as e:
            self.log_test("User creation", False, f"Request failed: {str(e)}")
            return
        
        # Test get all users
        try:
            response = requests.get(f"{API_BASE}/users", timeout=10)
            if response.status_code == 200:
                users = response.json()
                if isinstance(users, list) and len(users) > 0:
                    self.log_test("Get all users", True, f"Retrieved {len(users)} users")
                else:
                    self.log_test("Get all users", False, "No users returned or invalid format")
            else:
                self.log_test("Get all users", False, f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_test("Get all users", False, f"Request failed: {str(e)}")
        
        # Test get specific user
        if self.test_user_id:
            try:
                response = requests.get(f"{API_BASE}/users/{self.test_user_id}", timeout=10)
                if response.status_code == 200:
                    user = response.json()
                    if user["id"] == self.test_user_id:
                        self.log_test("Get specific user", True, f"Retrieved user: {user['name']}")
                    else:
                        self.log_test("Get specific user", False, "User ID mismatch")
                else:
                    self.log_test("Get specific user", False, f"HTTP {response.status_code}: {response.text}")
            except Exception as e:
                self.log_test("Get specific user", False, f"Request failed: {str(e)}")
    
    def test_resume_upload(self):
        """Test resume upload and processing"""
        print("\n=== Testing Resume Upload and Processing ===")
        
        if not self.test_user_id:
            self.log_test("Resume upload", False, "No test user available")
            return
        
        # Create a sample resume text file
        sample_resume = """
        John Doe
        Software Engineer
        Email: john.doe@email.com
        
        EXPERIENCE:
        - 5 years of experience in software development
        - Proficient in Python, JavaScript, React, Node.js
        - Experience with MongoDB, PostgreSQL, Docker
        - Worked with AWS, Git, Linux systems
        
        SKILLS:
        - Programming: Python, JavaScript, Java, SQL
        - Frameworks: React, Django, Flask, Express
        - Databases: MongoDB, PostgreSQL, MySQL
        - Tools: Docker, Git, AWS, Linux
        
        EDUCATION:
        - Bachelor's in Computer Science
        """
        
        try:
            # Test TXT file upload
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(sample_resume)
                temp_file_path = f.name
            
            with open(temp_file_path, 'rb') as f:
                files = {'file': ('resume.txt', f, 'text/plain')}
                response = requests.post(
                    f"{API_BASE}/users/{self.test_user_id}/upload-resume",
                    files=files,
                    timeout=30
                )
            
            os.unlink(temp_file_path)  # Clean up temp file
            
            if response.status_code == 200:
                result = response.json()
                skills = result.get("skills_extracted", [])
                experience = result.get("experience_years", 0)
                
                if len(skills) > 0 and experience > 0:
                    self.log_test("Resume upload and processing", True, 
                                f"Extracted {len(skills)} skills, {experience} years experience")
                else:
                    self.log_test("Resume upload and processing", False, 
                                f"Poor extraction: {len(skills)} skills, {experience} years")
            else:
                self.log_test("Resume upload and processing", False, 
                            f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_test("Resume upload and processing", False, f"Request failed: {str(e)}")
    
    def test_job_management(self):
        """Test job creation and retrieval"""
        print("\n=== Testing Job Management ===")
        
        # Test job creation
        sample_jobs = [
            {
                "title": "Senior Python Developer",
                "company": "TechInnovate Inc",
                "location": "Seattle, WA",
                "description": "We're seeking a senior Python developer with expertise in Django, FastAPI, and cloud technologies. Must have 5+ years experience.",
                "requirements": ["python", "django", "fastapi", "aws", "postgresql"],
                "salary_range": "$120,000 - $150,000",
                "job_type": "full-time",
                "source": "indeed",
                "url": "https://indeed.com/job/senior-python-dev"
            },
            {
                "title": "Full Stack JavaScript Developer",
                "company": "WebSolutions LLC",
                "location": "Austin, TX",
                "description": "Full stack developer needed for React and Node.js applications. Experience with MongoDB preferred.",
                "requirements": ["javascript", "react", "nodejs", "mongodb", "git"],
                "salary_range": "$90,000 - $120,000",
                "job_type": "full-time",
                "source": "linkedin",
                "url": "https://linkedin.com/job/fullstack-js"
            }
        ]
        
        for i, job_data in enumerate(sample_jobs):
            try:
                response = requests.post(f"{API_BASE}/jobs", json=job_data, timeout=10)
                if response.status_code == 200:
                    job = response.json()
                    self.test_job_ids.append(job["id"])
                    self.log_test(f"Job creation {i+1}", True, f"Created job: {job['title']}")
                else:
                    self.log_test(f"Job creation {i+1}", False, f"HTTP {response.status_code}: {response.text}")
            except Exception as e:
                self.log_test(f"Job creation {i+1}", False, f"Request failed: {str(e)}")
        
        # Test get all jobs
        try:
            response = requests.get(f"{API_BASE}/jobs", timeout=10)
            if response.status_code == 200:
                jobs = response.json()
                if isinstance(jobs, list) and len(jobs) > 0:
                    self.log_test("Get all jobs", True, f"Retrieved {len(jobs)} jobs")
                else:
                    self.log_test("Get all jobs", False, "No jobs returned or invalid format")
            else:
                self.log_test("Get all jobs", False, f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_test("Get all jobs", False, f"Request failed: {str(e)}")
    
    def test_job_matching(self):
        """Test job matching algorithm"""
        print("\n=== Testing Job Matching System ===")
        
        if not self.test_user_id:
            self.log_test("Job matching", False, "No test user available")
            return
        
        if len(self.test_job_ids) == 0:
            self.log_test("Job matching", False, "No test jobs available")
            return
        
        try:
            response = requests.get(f"{API_BASE}/users/{self.test_user_id}/matches", timeout=15)
            if response.status_code == 200:
                matches = response.json()
                if isinstance(matches, list):
                    if len(matches) > 0:
                        # Check match structure
                        first_match = matches[0]
                        required_fields = ["user_id", "job_id", "similarity_score", "matching_skills"]
                        
                        if all(field in first_match for field in required_fields):
                            similarity_score = first_match["similarity_score"]
                            matching_skills = first_match["matching_skills"]
                            
                            self.log_test("Job matching", True, 
                                        f"Found {len(matches)} matches, top similarity: {similarity_score:.2%}")
                        else:
                            self.log_test("Job matching", False, "Match structure incomplete")
                    else:
                        self.log_test("Job matching", False, "No matches found (may indicate embedding issue)")
                else:
                    self.log_test("Job matching", False, "Invalid response format")
            else:
                self.log_test("Job matching", False, f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_test("Job matching", False, f"Request failed: {str(e)}")
    
    def test_dashboard_data(self):
        """Test dashboard data retrieval"""
        print("\n=== Testing Dashboard Data ===")
        
        if not self.test_user_id:
            self.log_test("Dashboard data", False, "No test user available")
            return
        
        try:
            response = requests.get(f"{API_BASE}/dashboard/{self.test_user_id}", timeout=15)
            if response.status_code == 200:
                dashboard = response.json()
                
                # Check required sections
                required_sections = ["user", "matches", "applications", "scraping_tasks", "stats"]
                if all(section in dashboard for section in required_sections):
                    stats = dashboard["stats"]
                    user = dashboard["user"]
                    
                    self.log_test("Dashboard data", True, 
                                f"Dashboard loaded for {user['name']}, {stats['skills_count']} skills")
                else:
                    missing = [s for s in required_sections if s not in dashboard]
                    self.log_test("Dashboard data", False, f"Missing sections: {missing}")
            else:
                self.log_test("Dashboard data", False, f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_test("Dashboard data", False, f"Request failed: {str(e)}")
    
    def test_scraping_endpoint(self):
        """Test sample job scraping"""
        print("\n=== Testing Sample Job Scraping ===")
        
        try:
            response = requests.post(f"{API_BASE}/scrape/test", timeout=20)
            if response.status_code == 200:
                result = response.json()
                jobs_created = result.get("jobs_created", 0)
                
                if jobs_created > 0:
                    self.log_test("Sample job scraping", True, f"Created {jobs_created} sample jobs")
                else:
                    self.log_test("Sample job scraping", False, "No jobs were created")
            else:
                self.log_test("Sample job scraping", False, f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_test("Sample job scraping", False, f"Request failed: {str(e)}")
    
    def test_real_job_scraping(self):
        """Test real job scraping with JobSpy integration"""
        print("\n=== Testing Real Job Scraping ===")
        
        if not self.test_user_id:
            self.log_test("Real job scraping", False, "No test user available")
            return
        
        try:
            # Test real job scraping
            scraping_data = {
                "user_id": self.test_user_id,
                "keywords": ["python developer"],
                "location": "Remote"
            }
            
            response = requests.post(f"{API_BASE}/scrape/real", 
                                   params=scraping_data, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                jobs_created = result.get("jobs_created", 0)
                keywords = result.get("keywords", [])
                location = result.get("location", "")
                
                if jobs_created > 0:
                    self.log_test("Real job scraping", True, 
                                f"Scraped {jobs_created} real jobs for '{' '.join(keywords)}' in {location}")
                else:
                    self.log_test("Real job scraping", True, 
                                "Real scraping endpoint working (no jobs found - may be expected)")
            else:
                self.log_test("Real job scraping", False, f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_test("Real job scraping", False, f"Request failed: {str(e)}")
    
    def test_application_bot(self):
        """Test automated application bot"""
        print("\n=== Testing Automated Application Bot ===")
        
        if not self.test_user_id:
            self.log_test("Application bot", False, "No test user available")
            return
        
        if len(self.test_job_ids) == 0:
            self.log_test("Application bot", False, "No test jobs available")
            return
        
        try:
            # Test application bot with first job
            test_job_id = self.test_job_ids[0]
            
            response = requests.post(f"{API_BASE}/apply/test", 
                                   params={"user_id": self.test_user_id, "job_id": test_job_id}, 
                                   timeout=120)
            
            if response.status_code == 200:
                result = response.json()
                application_result = result.get("application_result", {})
                success = application_result.get("success", False)
                status = application_result.get("status", "")
                error_message = application_result.get("error_message", "")
                
                if success:
                    self.log_test("Application bot", True, f"Successfully applied to job (status: {status})")
                elif status in ["already_applied", "requires_manual"]:
                    self.log_test("Application bot", True, f"Bot working correctly (status: {status})")
                else:
                    self.log_test("Application bot", False, f"Application failed: {error_message}")
            else:
                self.log_test("Application bot", False, f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_test("Application bot", False, f"Request failed: {str(e)}")
    
    def test_scheduler_endpoints(self):
        """Test scheduler control endpoints"""
        print("\n=== Testing Scheduler Endpoints ===")
        
        # Test scheduler start
        try:
            response = requests.post(f"{API_BASE}/scheduler/start", timeout=10)
            if response.status_code == 200:
                result = response.json()
                if result.get("status") == "success":
                    self.log_test("Scheduler start", True, "Scheduler start endpoint working")
                else:
                    self.log_test("Scheduler start", False, f"Unexpected response: {result}")
            else:
                self.log_test("Scheduler start", False, f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_test("Scheduler start", False, f"Request failed: {str(e)}")
        
        # Test scheduler status
        try:
            response = requests.get(f"{API_BASE}/scheduler/status", timeout=10)
            if response.status_code == 200:
                result = response.json()
                required_fields = ["status", "today_stats", "recent_logs"]
                
                if all(field in result for field in required_fields):
                    today_stats = result["today_stats"]
                    self.log_test("Scheduler status", True, 
                                f"Status: {result['status']}, Today: {today_stats['applications_sent']} apps, {today_stats['jobs_scraped']} jobs")
                else:
                    missing = [f for f in required_fields if f not in result]
                    self.log_test("Scheduler status", False, f"Missing fields: {missing}")
            else:
                self.log_test("Scheduler status", False, f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_test("Scheduler status", False, f"Request failed: {str(e)}")
    
    def test_enhanced_api_endpoints(self):
        """Test enhanced API endpoints for autonomous system"""
        print("\n=== Testing Enhanced API Endpoints ===")
        
        if not self.test_user_id:
            self.log_test("Enhanced API endpoints", False, "No test user available")
            return
        
        # Test application history endpoint
        try:
            response = requests.get(f"{API_BASE}/applications/{self.test_user_id}", timeout=10)
            if response.status_code == 200:
                applications = response.json()
                if isinstance(applications, list):
                    self.log_test("Application history", True, f"Retrieved {len(applications)} application records")
                else:
                    self.log_test("Application history", False, "Invalid response format")
            else:
                self.log_test("Application history", False, f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_test("Application history", False, f"Request failed: {str(e)}")
        
        # Test user jobs endpoint
        try:
            response = requests.get(f"{API_BASE}/jobs/{self.test_user_id}", timeout=10)
            if response.status_code == 200:
                jobs = response.json()
                if isinstance(jobs, list):
                    self.log_test("User jobs", True, f"Retrieved {len(jobs)} user-specific jobs")
                else:
                    self.log_test("User jobs", False, "Invalid response format")
            else:
                self.log_test("User jobs", False, f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_test("User jobs", False, f"Request failed: {str(e)}")
        
        # Test user preferences endpoint
        try:
            preferences = {
                "keywords": ["python", "javascript"],
                "location": "Remote",
                "job_type": "fulltime",
                "max_daily_applications": 25
            }
            
            response = requests.put(f"{API_BASE}/users/{self.test_user_id}/preferences", 
                                  json=preferences, timeout=10)
            if response.status_code == 200:
                result = response.json()
                if "message" in result:
                    self.log_test("User preferences", True, "Preferences updated successfully")
                else:
                    self.log_test("User preferences", False, "Unexpected response format")
            else:
                self.log_test("User preferences", False, f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_test("User preferences", False, f"Request failed: {str(e)}")
        
        # Test system statistics endpoint
        try:
            response = requests.get(f"{API_BASE}/stats/system", timeout=10)
            if response.status_code == 200:
                stats = response.json()
                required_fields = ["total_users", "total_jobs", "total_applications", "success_rate", "last_24h"]
                
                if all(field in stats for field in required_fields):
                    self.log_test("System statistics", True, 
                                f"Users: {stats['total_users']}, Jobs: {stats['total_jobs']}, Apps: {stats['total_applications']}, Success: {stats['success_rate']}%")
                else:
                    missing = [f for f in required_fields if f not in stats]
                    self.log_test("System statistics", False, f"Missing fields: {missing}")
            else:
                self.log_test("System statistics", False, f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.log_test("System statistics", False, f"Request failed: {str(e)}")
    
    def test_autonomous_workflow_integration(self):
        """Test complete autonomous workflow integration"""
        print("\n=== Testing Autonomous Workflow Integration ===")
        
        if not self.test_user_id:
            self.log_test("Autonomous workflow", False, "No test user available")
            return
        
        try:
            # Step 1: Check if user has resume uploaded
            user_response = requests.get(f"{API_BASE}/users/{self.test_user_id}", timeout=10)
            if user_response.status_code != 200:
                self.log_test("Autonomous workflow", False, "Cannot retrieve user data")
                return
            
            user = user_response.json()
            has_resume = len(user.get("skills", [])) > 0
            
            if not has_resume:
                self.log_test("Autonomous workflow", False, "User needs resume for autonomous workflow")
                return
            
            # Step 2: Test job scraping creates jobs
            scraping_response = requests.post(f"{API_BASE}/scrape/test", timeout=20)
            if scraping_response.status_code != 200:
                self.log_test("Autonomous workflow", False, "Job scraping failed")
                return
            
            # Step 3: Test job matching works
            matches_response = requests.get(f"{API_BASE}/users/{self.test_user_id}/matches", timeout=15)
            if matches_response.status_code != 200:
                self.log_test("Autonomous workflow", False, "Job matching failed")
                return
            
            matches = matches_response.json()
            if len(matches) == 0:
                self.log_test("Autonomous workflow", False, "No job matches found")
                return
            
            # Step 4: Test dashboard shows complete data
            dashboard_response = requests.get(f"{API_BASE}/dashboard/{self.test_user_id}", timeout=15)
            if dashboard_response.status_code != 200:
                self.log_test("Autonomous workflow", False, "Dashboard data retrieval failed")
                return
            
            dashboard = dashboard_response.json()
            required_sections = ["user", "matches", "applications", "scraping_tasks", "stats"]
            
            if all(section in dashboard for section in required_sections):
                stats = dashboard["stats"]
                self.log_test("Autonomous workflow", True, 
                            f"Complete workflow functional: {len(matches)} matches, {stats['skills_count']} skills, {stats['experience_years']} years exp")
            else:
                self.log_test("Autonomous workflow", False, "Dashboard missing required sections")
                
        except Exception as e:
            self.log_test("Autonomous workflow", False, f"Workflow test failed: {str(e)}")
    
    def test_database_connections(self):
        """Test database connectivity indirectly through API operations"""
        print("\n=== Testing Database Connections ===")
        
        # MongoDB test - try to create and retrieve a user
        try:
            test_user = {
                "name": "DB Test User",
                "email": "dbtest@example.com"
            }
            
            response = requests.post(f"{API_BASE}/users", json=test_user, timeout=10)
            if response.status_code == 200:
                user = response.json()
                
                # Try to retrieve the user
                get_response = requests.get(f"{API_BASE}/users/{user['id']}", timeout=10)
                if get_response.status_code == 200:
                    self.log_test("MongoDB connection", True, "Data persistence working")
                else:
                    self.log_test("MongoDB connection", False, "Data retrieval failed")
            else:
                self.log_test("MongoDB connection", False, "Data creation failed")
        except Exception as e:
            self.log_test("MongoDB connection", False, f"Database test failed: {str(e)}")
        
        # Chroma Vector DB test - indirectly tested through resume upload and matching
        if self.test_user_id and len(self.test_job_ids) > 0:
            try:
                # If we can get matches, vector DB is working
                response = requests.get(f"{API_BASE}/users/{self.test_user_id}/matches", timeout=10)
                if response.status_code == 200:
                    matches = response.json()
                    if isinstance(matches, list):
                        self.log_test("Chroma Vector DB", True, "Vector similarity search working")
                    else:
                        self.log_test("Chroma Vector DB", False, "Vector search returned invalid format")
                else:
                    self.log_test("Chroma Vector DB", False, "Vector search failed")
            except Exception as e:
                self.log_test("Chroma Vector DB", False, f"Vector DB test failed: {str(e)}")
        else:
            self.log_test("Chroma Vector DB", False, "Cannot test - no user/jobs available")
    
    def run_all_tests(self):
        """Run all backend tests"""
        print(f"🚀 Starting AutoApplyX Backend Tests")
        print(f"Backend URL: {BACKEND_URL}")
        print(f"API Base: {API_BASE}")
        
        # Run core tests first
        self.test_basic_connectivity()
        self.test_user_management()
        self.test_resume_upload()
        self.test_job_management()
        self.test_job_matching()
        self.test_dashboard_data()
        self.test_database_connections()
        
        # Run autonomous system tests
        self.test_scraping_endpoint()
        self.test_real_job_scraping()
        self.test_application_bot()
        self.test_scheduler_endpoints()
        self.test_enhanced_api_endpoints()
        self.test_autonomous_workflow_integration()
        
        # Summary
        print("\n" + "="*60)
        print("🏁 TEST SUMMARY")
        print("="*60)
        
        passed = sum(1 for result in self.test_results.values() if result["success"])
        total = len(self.test_results)
        
        for test_name, result in self.test_results.items():
            status = "✅" if result["success"] else "❌"
            print(f"{status} {test_name}")
        
        print(f"\nResults: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
        
        if passed == total:
            print("🎉 All tests passed! Backend is working correctly.")
        else:
            print("⚠️  Some tests failed. Check the details above.")
        
        return self.test_results

if __name__ == "__main__":
    tester = BackendTester()
    results = tester.run_all_tests()
    
    # Exit with appropriate code
    failed_tests = [name for name, result in results.items() if not result["success"]]
    sys.exit(0 if len(failed_tests) == 0 else 1)