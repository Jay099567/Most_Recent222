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
        
        # Run tests in logical order
        self.test_basic_connectivity()
        self.test_user_management()
        self.test_resume_upload()
        self.test_job_management()
        self.test_job_matching()
        self.test_dashboard_data()
        self.test_scraping_endpoint()
        self.test_database_connections()
        
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