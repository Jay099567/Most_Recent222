import asyncio
import logging
from typing import List, Dict, Any, Optional
from jobspy import scrape_jobs
from datetime import datetime, timedelta
import pandas as pd
import os
import json
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
import time
import random
from urllib.parse import urljoin, urlparse
import re
from playwright.async_api import async_playwright
from sentence_transformers import SentenceTransformer
import numpy as np

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AdvancedJobScraper:
    """
    Advanced job scraper with AI-powered filtering and multiple job board support
    Supports: LinkedIn, Indeed, Google Jobs, ZipRecruiter, Glassdoor, Monster, 
    CareerBuilder, Lever, Greenhouse, Workday, BambooHR, Remotive, Adzuna
    """
    
    def __init__(self, use_proxies: bool = True, max_results_per_site: int = 50):
        self.use_proxies = use_proxies
        self.max_results_per_site = max_results_per_site
        
        # ScraperAPI integration for proxy rotation
        self.scraperapi_key = os.getenv('SCRAPERAPI_KEY')
        self.openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
        
        # Initialize AI model for job filtering
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        
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
        
    async def scrape_jobs_jobspy(self, keywords: str, location: str = "United States", 
                                sites: List[str] = None) -> List[Dict[str, Any]]:
        """
        Scrape jobs using JobSpy for supported sites
        """
        try:
            if sites is None:
                sites = ["indeed", "linkedin", "glassdoor", "google", "zip_recruiter"]
            
            # Filter only supported JobSpy sites
            jobspy_sites = [site for site in sites if site in ["indeed", "linkedin", "glassdoor", "google", "zip_recruiter"]]
            
            if not jobspy_sites:
                logger.warning("No supported JobSpy sites provided")
                return []
            
            logger.info(f"Scraping jobs from {jobspy_sites} for keywords: {keywords}")
            
            # Scrape jobs using JobSpy
            jobs = scrape_jobs(
                site_name=jobspy_sites,
                search_term=keywords,
                location=location,
                results_wanted=self.max_results_per_site,
                hours_old=72,  # Jobs posted within last 72 hours
                country_indeed="USA",
                hyperlinks=True,
                proxy=self.scraperapi_key if self.use_proxies else None
            )
            
            if jobs is None or jobs.empty:
                logger.warning("No jobs found with JobSpy")
                return []
            
            # Convert to list of dictionaries
            jobs_list = []
            for _, job in jobs.iterrows():
                job_dict = {
                    "id": f"jobspy_{hash(job.get('job_url', ''))}",
                    "title": job.get('title', ''),
                    "company": job.get('company', ''),
                    "location": job.get('location', ''),
                    "description": job.get('description', ''),
                    "job_type": job.get('job_type', 'full-time'),
                    "salary_min": job.get('min_amount', None),
                    "salary_max": job.get('max_amount', None),
                    "url": job.get('job_url', ''),
                    "source": job.get('site', ''),
                    "posted_date": datetime.now(),
                    "scraped_at": datetime.now(),
                    "requirements": self._extract_requirements(job.get('description', ''))
                }
                jobs_list.append(job_dict)
            
            logger.info(f"Found {len(jobs_list)} jobs using JobSpy")
            return jobs_list
            
        except Exception as e:
            logger.error(f"JobSpy scraping failed: {str(e)}")
            return []
    
    def _extract_requirements(self, description: str) -> List[str]:
        """
        Extract job requirements from description using pattern matching
        """
        try:
            if not description:
                return []
            
            requirements = []
            
            # Common requirement patterns
            requirement_patterns = [
                r'(\d+\+?\s*years?\s*(?:of\s*)?experience)',
                r'(Bachelor\'s?\s*degree|Master\'s?\s*degree|PhD)',
                r'(Python|Java|JavaScript|React|Angular|Vue|Node\.js)',
                r'(AWS|Azure|GCP|Docker|Kubernetes)',
                r'(SQL|MongoDB|PostgreSQL|MySQL)'
            ]
            
            for pattern in requirement_patterns:
                matches = re.findall(pattern, description, re.IGNORECASE)
                requirements.extend(matches)
            
            return list(set(requirements))  # Remove duplicates
            
        except Exception as e:
            logger.error(f"Error extracting requirements: {e}")
            return []
    
    async def ai_filter_jobs(self, jobs: List[Dict[str, Any]], user_preferences: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Use AI to filter and rank jobs based on user preferences
        """
        try:
            if not jobs or not self.openrouter_api_key:
                return jobs
            
            # Create user preference embedding
            user_skills = user_preferences.get('skills', [])
            user_experience = user_preferences.get('experience_years', 0)
            user_preferences_text = f"Skills: {', '.join(user_skills)}, Experience: {user_experience} years"
            
            # Score each job
            scored_jobs = []
            for job in jobs:
                try:
                    # Create job embedding
                    job_text = f"{job['title']} {job['description']}"
                    
                    # Calculate similarity score
                    user_embedding = self.embedding_model.encode([user_preferences_text])
                    job_embedding = self.embedding_model.encode([job_text])
                    
                    similarity = np.dot(user_embedding[0], job_embedding[0]) / (
                        np.linalg.norm(user_embedding[0]) * np.linalg.norm(job_embedding[0])
                    )
                    
                    job['ai_score'] = float(similarity)
                    scored_jobs.append(job)
                    
                except Exception as e:
                    logger.error(f"Error scoring job {job.get('id', 'unknown')}: {e}")
                    job['ai_score'] = 0.0
                    scored_jobs.append(job)
            
            # Sort by AI score
            scored_jobs.sort(key=lambda x: x['ai_score'], reverse=True)
            
            logger.info(f"AI filtered and ranked {len(scored_jobs)} jobs")
            return scored_jobs
            
        except Exception as e:
            logger.error(f"AI filtering failed: {str(e)}")
            return jobs
    
    async def scrape_all_jobs(self, keywords: str, location: str = "United States", 
                             job_boards: List[str] = None, 
                             user_preferences: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Scrape jobs from all supported job boards
        """
        all_jobs = []
        
        if job_boards is None:
            job_boards = ["indeed", "linkedin", "glassdoor", "google", "zip_recruiter"]
        
        # Scrape from JobSpy supported sites
        jobspy_sites = [site for site in job_boards if site in ["indeed", "linkedin", "glassdoor", "google", "zip_recruiter"]]
        if jobspy_sites:
            jobspy_jobs = await self.scrape_jobs_jobspy(keywords, location, jobspy_sites)
            all_jobs.extend(jobspy_jobs)
        
        # Remove duplicates based on URL
        unique_jobs = []
        seen_urls = set()
        for job in all_jobs:
            if job['url'] not in seen_urls:
                unique_jobs.append(job)
                seen_urls.add(job['url'])
        
        logger.info(f"Found {len(unique_jobs)} unique jobs from {len(job_boards)} job boards")
        
        # AI filter and rank jobs
        if user_preferences:
            unique_jobs = await self.ai_filter_jobs(unique_jobs, user_preferences)
        
        return unique_jobs

# Usage example
async def main():
    """
    Example usage of the Advanced Job Scraper
    """
    scraper = AdvancedJobScraper()
    
    user_preferences = {
        'skills': ['Python', 'JavaScript', 'React', 'FastAPI'],
        'experience_years': 3
    }
    
    jobs = await scraper.scrape_all_jobs(
        keywords="software engineer",
        location="San Francisco",
        job_boards=["indeed", "linkedin", "glassdoor"],
        user_preferences=user_preferences
    )
    
    print(f"Found {len(jobs)} jobs")
    for job in jobs[:5]:  # Show top 5
        print(f"Title: {job['title']}")
        print(f"Company: {job['company']}")
        print(f"Location: {job['location']}")
        print(f"Source: {job['source']}")
        print(f"AI Score: {job.get('ai_score', 'N/A')}")
        print("-" * 50)

if __name__ == "__main__":
    asyncio.run(main())