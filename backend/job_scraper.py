import asyncio
import logging
from typing import List, Dict, Any, Optional
from jobspy import scrape_jobs
from datetime import datetime, timedelta
import pandas as pd
import os
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class JobScraper:
    """
    Real job scraper using JobSpy library
    Supports Indeed, LinkedIn, Glassdoor, Google, ZipRecruiter, Bayt, and Naukri
    """
    
    def __init__(self, use_proxies: bool = True, max_results_per_site: int = 100):
        self.use_proxies = use_proxies
        self.max_results_per_site = max_results_per_site
        
        # ScraperAPI integration for proxy rotation
        self.scraperapi_key = os.getenv('SCRAPERAPI_KEY')
        self.proxies = self._get_proxies() if use_proxies else None
        
        # Supported job sites
        self.supported_sites = [
            "indeed", "linkedin", "glassdoor", "google", 
            "zip_recruiter", "bayt", "naukri"
        ]
        
    def _get_proxies(self) -> Optional[List[str]]:
        """Get proxy list using ScraperAPI"""
        if not self.scraperapi_key:
            logger.warning("ScraperAPI key not found. Running without proxies.")
            return None
            
        # ScraperAPI provides rotating proxies
        proxy_endpoints = [
            f"scraperapi:{self.scraperapi_key}@proxy-server.scraperapi.com:8001",
            f"scraperapi:{self.scraperapi_key}@proxy-server.scraperapi.com:8002",
            f"scraperapi:{self.scraperapi_key}@proxy-server.scraperapi.com:8003",
        ]
        
        return proxy_endpoints
    
    async def scrape_jobs_for_user(
        self, 
        user_preferences: Dict[str, Any],
        max_jobs_per_site: int = None
    ) -> List[Dict[str, Any]]:
        """
        Scrape jobs based on user preferences
        
        Args:
            user_preferences: Dict containing search_terms, location, job_type, etc.
            max_jobs_per_site: Maximum jobs to scrape per site
            
        Returns:
            List of job dictionaries
        """
        try:
            max_jobs = max_jobs_per_site or self.max_results_per_site
            
            # Extract search parameters from user preferences
            search_terms = user_preferences.get('keywords', ['software engineer'])
            location = user_preferences.get('location', 'Remote')
            job_type = user_preferences.get('job_type', 'fulltime')
            is_remote = user_preferences.get('is_remote', True)
            hours_old = user_preferences.get('hours_old', 72)  # Last 3 days
            
            # Convert list to string for search
            search_term = ' '.join(search_terms) if isinstance(search_terms, list) else search_terms
            
            logger.info(f"Scraping jobs for: {search_term} in {location}")
            
            # Scrape jobs from all supported sites
            jobs_df = scrape_jobs(
                site_name=self.supported_sites,
                search_term=search_term,
                location=location,
                job_type=job_type,
                is_remote=is_remote,
                results_wanted=max_jobs,
                hours_old=hours_old,
                proxies=self.proxies,
                verbose=1,  # Show warnings and errors
                description_format="markdown",
                linkedin_fetch_description=True,  # Get full descriptions
                country_indeed='USA',  # Focus on US jobs for Indeed
                enforce_annual_salary=True  # Convert to annual salary
            )
            
            if jobs_df.empty:
                logger.warning("No jobs found for the given criteria")
                return []
                
            # Convert DataFrame to list of dictionaries
            jobs_list = []
            for _, row in jobs_df.iterrows():
                job_dict = {
                    "title": row.get('title', ''),
                    "company": row.get('company', ''),
                    "location": row.get('location', ''),
                    "description": row.get('description', ''),
                    "job_url": row.get('job_url', ''),
                    "source": row.get('site', ''),
                    "job_type": row.get('job_type', 'fulltime'),
                    "salary_min": row.get('min_amount', None),
                    "salary_max": row.get('max_amount', None),
                    "salary_currency": row.get('currency', 'USD'),
                    "salary_interval": row.get('interval', 'yearly'),
                    "is_remote": row.get('is_remote', False),
                    "date_posted": row.get('date_posted', datetime.utcnow()),
                    "company_url": row.get('company_url', ''),
                    "emails": row.get('emails', []),
                    "requirements": self._extract_requirements(row.get('description', '')),
                    "scraped_at": datetime.utcnow()
                }
                jobs_list.append(job_dict)
                
            logger.info(f"Successfully scraped {len(jobs_list)} jobs")
            return jobs_list
            
        except Exception as e:
            logger.error(f"Error scraping jobs: {str(e)}")
            return []
    
    def _extract_requirements(self, description: str) -> List[str]:
        """Extract technical requirements from job description"""
        if not description:
            return []
            
        # Common tech skills to look for
        tech_skills = [
            'python', 'java', 'javascript', 'react', 'nodejs', 'angular', 'vue',
            'html', 'css', 'sql', 'mongodb', 'postgresql', 'mysql', 'docker',
            'kubernetes', 'aws', 'azure', 'gcp', 'git', 'linux', 'bash',
            'tensorflow', 'pytorch', 'pandas', 'numpy', 'fastapi', 'django',
            'flask', 'spring', 'express', 'bootstrap', 'tailwind', 'typescript',
            'c++', 'c#', 'go', 'rust', 'php', 'ruby', 'scala', 'kotlin',
            'swift', 'flutter', 'react native', 'unity', 'firebase', 'redis',
            'elasticsearch', 'jenkins', 'terraform', 'ansible', 'prometheus',
            'grafana', 'microservices', 'rest api', 'graphql', 'websocket'
        ]
        
        description_lower = description.lower()
        found_skills = []
        
        for skill in tech_skills:
            if skill in description_lower:
                found_skills.append(skill)
                
        return found_skills
    
    async def scrape_jobs_by_keywords(
        self, 
        keywords: List[str],
        location: str = "Remote",
        max_jobs: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Scrape jobs for specific keywords
        
        Args:
            keywords: List of job search keywords
            location: Job location
            max_jobs: Maximum number of jobs to scrape
            
        Returns:
            List of job dictionaries
        """
        user_preferences = {
            'keywords': keywords,
            'location': location,
            'job_type': 'fulltime',
            'is_remote': True,
            'hours_old': 24  # Last 24 hours for more recent jobs
        }
        
        return await self.scrape_jobs_for_user(user_preferences, max_jobs)
    
    async def scrape_jobs_bulk(
        self, 
        user_preferences_list: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Scrape jobs for multiple users concurrently
        
        Args:
            user_preferences_list: List of user preference dictionaries
            
        Returns:
            Dictionary mapping user IDs to their scraped jobs
        """
        results = {}
        
        # Create async tasks for each user
        tasks = []
        for user_prefs in user_preferences_list:
            user_id = user_prefs.get('user_id')
            if user_id:
                task = asyncio.create_task(
                    self.scrape_jobs_for_user(user_prefs),
                    name=f"scrape_user_{user_id}"
                )
                tasks.append((user_id, task))
        
        # Execute all tasks concurrently
        for user_id, task in tasks:
            try:
                jobs = await task
                results[user_id] = jobs
                logger.info(f"Scraped {len(jobs)} jobs for user {user_id}")
            except Exception as e:
                logger.error(f"Error scraping jobs for user {user_id}: {str(e)}")
                results[user_id] = []
        
        return results
    
    def get_supported_sites(self) -> List[str]:
        """Get list of supported job sites"""
        return self.supported_sites.copy()
    
    def get_scraper_stats(self) -> Dict[str, Any]:
        """Get scraper configuration and stats"""
        return {
            "supported_sites": self.supported_sites,
            "max_results_per_site": self.max_results_per_site,
            "proxies_enabled": self.use_proxies,
            "scraperapi_configured": bool(self.scraperapi_key)
        }

# Example usage for testing
async def test_scraper():
    """Test function for the job scraper"""
    scraper = JobScraper(use_proxies=True, max_results_per_site=10)
    
    # Test scraping
    user_preferences = {
        'keywords': ['software engineer', 'python'],
        'location': 'San Francisco, CA',
        'job_type': 'fulltime',
        'is_remote': True,
        'hours_old': 24
    }
    
    jobs = await scraper.scrape_jobs_for_user(user_preferences)
    print(f"Found {len(jobs)} jobs")
    
    for job in jobs[:3]:  # Show first 3 jobs
        print(f"Title: {job['title']}")
        print(f"Company: {job['company']}")
        print(f"Location: {job['location']}")
        print(f"Source: {job['source']}")
        print(f"Requirements: {job['requirements']}")
        print("-" * 50)

if __name__ == "__main__":
    asyncio.run(test_scraper())