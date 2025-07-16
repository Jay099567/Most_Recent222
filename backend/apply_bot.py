import asyncio
import logging
from typing import Dict, List, Any, Optional, Tuple
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from datetime import datetime, timedelta
import json
import random
import time
import re
from urllib.parse import urlparse, parse_qs
from dataclasses import dataclass
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ApplicationResult:
    """Result of a job application attempt"""
    job_id: str
    job_url: str
    success: bool
    status: str  # 'applied', 'failed', 'requires_manual', 'already_applied'
    error_message: Optional[str] = None
    application_id: Optional[str] = None
    screenshot_path: Optional[str] = None
    retry_count: int = 0
    applied_at: datetime = None

class JobApplicationBot:
    """
    Automated job application bot using Playwright
    Supports multiple job boards with anti-detection measures
    """
    
    def __init__(self, headless: bool = True, max_retries: int = 3):
        self.headless = headless
        self.max_retries = max_retries
        self.browser = None
        self.context = None
        
        # User agents for rotation
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]
        
        # Application strategies for different sites
        self.application_strategies = {
            'indeed': self._apply_indeed,
            'linkedin': self._apply_linkedin,
            'glassdoor': self._apply_glassdoor,
            'google': self._apply_google,
            'zip_recruiter': self._apply_ziprecruiter,
            'bayt': self._apply_bayt,
            'naukri': self._apply_naukri
        }
        
        # Common form field mappings
        self.form_fields = {
            'email': ['email', 'email_address', 'user_email', 'contact_email'],
            'phone': ['phone', 'phone_number', 'contact_phone', 'mobile'],
            'first_name': ['first_name', 'firstname', 'fname', 'given_name'],
            'last_name': ['last_name', 'lastname', 'lname', 'family_name'],
            'full_name': ['full_name', 'name', 'fullname', 'candidate_name'],
            'resume': ['resume', 'cv', 'resume_file', 'cv_file', 'attachment'],
            'cover_letter': ['cover_letter', 'coverletter', 'letter', 'message'],
            'linkedin_url': ['linkedin', 'linkedin_url', 'linkedin_profile', 'profile_url'],
            'portfolio_url': ['portfolio', 'portfolio_url', 'website', 'personal_website'],
            'salary_expectation': ['salary', 'expected_salary', 'salary_expectation', 'desired_salary'],
            'availability': ['availability', 'start_date', 'available_date', 'notice_period']
        }
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self.start_browser()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close_browser()
        
    async def start_browser(self):
        """Start Playwright browser with anti-detection settings"""
        try:
            self.playwright = await async_playwright().start()
            
            # Launch browser with anti-detection settings
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--disable-gpu',
                    '--window-size=1920,1080',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor',
                    '--disable-blink-features=AutomationControlled'
                ]
            )
            
            # Create context with random user agent
            self.context = await self.browser.new_context(
                user_agent=random.choice(self.user_agents),
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                timezone_id='America/New_York'
            )
            
            # Add stealth settings
            await self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });
                
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                });
                
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                
                window.chrome = {
                    runtime: {},
                };
            """)
            
            logger.info("Browser started successfully")
            
        except Exception as e:
            logger.error(f"Error starting browser: {str(e)}")
            raise
    
    async def close_browser(self):
        """Close browser and cleanup"""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if hasattr(self, 'playwright'):
                await self.playwright.stop()
            logger.info("Browser closed successfully")
        except Exception as e:
            logger.error(f"Error closing browser: {str(e)}")
    
    async def apply_to_job(
        self, 
        job_data: Dict[str, Any], 
        user_profile: Dict[str, Any]
    ) -> ApplicationResult:
        """
        Apply to a single job
        
        Args:
            job_data: Job information including URL, title, company, etc.
            user_profile: User profile with personal info and preferences
            
        Returns:
            ApplicationResult object with application status
        """
        job_url = job_data.get('job_url', '')
        job_id = job_data.get('id', '')
        source = job_data.get('source', '').lower()
        
        logger.info(f"Applying to job: {job_data.get('title', '')} at {job_data.get('company', '')}")
        
        # Determine application strategy based on source
        if source in self.application_strategies:
            strategy = self.application_strategies[source]
        else:
            # Generic application strategy
            strategy = self._apply_generic
        
        # Apply with retry logic
        for attempt in range(self.max_retries + 1):
            try:
                result = await strategy(job_data, user_profile)
                result.retry_count = attempt
                
                if result.success:
                    logger.info(f"Successfully applied to job {job_id}")
                    return result
                elif result.status == 'already_applied':
                    logger.info(f"Already applied to job {job_id}")
                    return result
                    
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed for job {job_id}: {str(e)}")
                if attempt < self.max_retries:
                    await asyncio.sleep(random.uniform(2, 5))  # Random delay
                else:
                    return ApplicationResult(
                        job_id=job_id,
                        job_url=job_url,
                        success=False,
                        status='failed',
                        error_message=str(e),
                        retry_count=attempt
                    )
        
        return ApplicationResult(
            job_id=job_id,
            job_url=job_url,
            success=False,
            status='failed',
            error_message='Max retries exceeded',
            retry_count=self.max_retries
        )
    
    async def _apply_indeed(self, job_data: Dict[str, Any], user_profile: Dict[str, Any]) -> ApplicationResult:
        """Apply to Indeed job"""
        try:
            page = await self.context.new_page()
            job_url = job_data['job_url']
            job_id = job_data['id']
            
            # Navigate to job page
            await page.goto(job_url, wait_until='networkidle')
            await self._random_delay()
            
            # Look for "Apply Now" button
            apply_selectors = [
                'button:has-text("Apply now")',
                'button:has-text("Apply")',
                'a:has-text("Apply now")',
                'a:has-text("Apply")',
                '[data-testid="apply-button"]',
                '.jobsearch-ApplyButton'
            ]
            
            apply_button = None
            for selector in apply_selectors:
                try:
                    apply_button = await page.wait_for_selector(selector, timeout=5000)
                    if apply_button:
                        break
                except:
                    continue
            
            if not apply_button:
                return ApplicationResult(
                    job_id=job_id,
                    job_url=job_url,
                    success=False,
                    status='failed',
                    error_message='Apply button not found'
                )
            
            # Click apply button
            await apply_button.click()
            await page.wait_for_timeout(3000)
            
            # Handle different application flows
            if 'indeed.com' in page.url:
                # Indeed native application
                result = await self._fill_indeed_form(page, user_profile)
            else:
                # External application
                result = await self._fill_generic_form(page, user_profile)
            
            if result:
                return ApplicationResult(
                    job_id=job_id,
                    job_url=job_url,
                    success=True,
                    status='applied',
                    applied_at=datetime.utcnow()
                )
            
            return ApplicationResult(
                job_id=job_id,
                job_url=job_url,
                success=False,
                status='failed',
                error_message='Form submission failed'
            )
            
        except Exception as e:
            logger.error(f"Error applying to Indeed job: {str(e)}")
            return ApplicationResult(
                job_id=job_id,
                job_url=job_url,
                success=False,
                status='failed',
                error_message=str(e)
            )
        finally:
            await page.close()
    
    async def _apply_linkedin(self, job_data: Dict[str, Any], user_profile: Dict[str, Any]) -> ApplicationResult:
        """Apply to LinkedIn job"""
        try:
            page = await self.context.new_page()
            job_url = job_data['job_url']
            job_id = job_data['id']
            
            # Navigate to job page
            await page.goto(job_url, wait_until='networkidle')
            await self._random_delay()
            
            # Look for Easy Apply button
            easy_apply_selectors = [
                'button:has-text("Easy Apply")',
                '[data-test-id="easy-apply-button"]',
                '.jobs-apply-button'
            ]
            
            easy_apply_button = None
            for selector in easy_apply_selectors:
                try:
                    easy_apply_button = await page.wait_for_selector(selector, timeout=5000)
                    if easy_apply_button:
                        break
                except:
                    continue
            
            if not easy_apply_button:
                return ApplicationResult(
                    job_id=job_id,
                    job_url=job_url,
                    success=False,
                    status='failed',
                    error_message='Easy Apply button not found'
                )
            
            # Click Easy Apply
            await easy_apply_button.click()
            await page.wait_for_timeout(3000)
            
            # Handle LinkedIn Easy Apply flow
            result = await self._fill_linkedin_easy_apply(page, user_profile)
            
            if result:
                return ApplicationResult(
                    job_id=job_id,
                    job_url=job_url,
                    success=True,
                    status='applied',
                    applied_at=datetime.utcnow()
                )
            
            return ApplicationResult(
                job_id=job_id,
                job_url=job_url,
                success=False,
                status='failed',
                error_message='LinkedIn Easy Apply failed'
            )
            
        except Exception as e:
            logger.error(f"Error applying to LinkedIn job: {str(e)}")
            return ApplicationResult(
                job_id=job_id,
                job_url=job_url,
                success=False,
                status='failed',
                error_message=str(e)
            )
        finally:
            await page.close()
    
    async def _apply_generic(self, job_data: Dict[str, Any], user_profile: Dict[str, Any]) -> ApplicationResult:
        """Generic application strategy for unknown sites"""
        try:
            page = await self.context.new_page()
            job_url = job_data['job_url']
            job_id = job_data['id']
            
            # Navigate to job page
            await page.goto(job_url, wait_until='networkidle')
            await self._random_delay()
            
            # Look for generic apply buttons
            apply_selectors = [
                'button:has-text("Apply")',
                'a:has-text("Apply")',
                'button:has-text("Submit Application")',
                'input[type="submit"][value*="Apply"]',
                '.apply-button',
                '#apply-button'
            ]
            
            apply_button = None
            for selector in apply_selectors:
                try:
                    apply_button = await page.wait_for_selector(selector, timeout=5000)
                    if apply_button:
                        break
                except:
                    continue
            
            if not apply_button:
                return ApplicationResult(
                    job_id=job_id,
                    job_url=job_url,
                    success=False,
                    status='failed',
                    error_message='Apply button not found'
                )
            
            # Click apply button
            await apply_button.click()
            await page.wait_for_timeout(3000)
            
            # Fill generic form
            result = await self._fill_generic_form(page, user_profile)
            
            if result:
                return ApplicationResult(
                    job_id=job_id,
                    job_url=job_url,
                    success=True,
                    status='applied',
                    applied_at=datetime.utcnow()
                )
            
            return ApplicationResult(
                job_id=job_id,
                job_url=job_url,
                success=False,
                status='failed',
                error_message='Generic form submission failed'
            )
            
        except Exception as e:
            logger.error(f"Error applying to generic job: {str(e)}")
            return ApplicationResult(
                job_id=job_id,
                job_url=job_url,
                success=False,
                status='failed',
                error_message=str(e)
            )
        finally:
            await page.close()
    
    async def _fill_generic_form(self, page: Page, user_profile: Dict[str, Any]) -> bool:
        """Fill generic job application form"""
        try:
            # Common form fields to fill
            form_data = {
                'email': user_profile.get('email', ''),
                'phone': user_profile.get('phone', ''),
                'first_name': user_profile.get('first_name', ''),
                'last_name': user_profile.get('last_name', ''),
                'full_name': user_profile.get('name', ''),
                'linkedin_url': user_profile.get('linkedin_url', ''),
                'portfolio_url': user_profile.get('portfolio_url', ''),
                'cover_letter': user_profile.get('cover_letter', ''),
                'salary_expectation': user_profile.get('salary_expectation', ''),
                'availability': user_profile.get('availability', 'Immediately')
            }
            
            # Fill form fields
            for field_type, field_names in self.form_fields.items():
                value = form_data.get(field_type, '')
                if value:
                    for field_name in field_names:
                        selectors = [
                            f'input[name="{field_name}"]',
                            f'input[id="{field_name}"]',
                            f'textarea[name="{field_name}"]',
                            f'textarea[id="{field_name}"]'
                        ]
                        
                        for selector in selectors:
                            try:
                                field = await page.wait_for_selector(selector, timeout=2000)
                                if field:
                                    await field.fill(value)
                                    await self._random_delay(0.5, 1.5)
                                    break
                            except:
                                continue
            
            # Handle file uploads (resume)
            resume_path = user_profile.get('resume_path')
            if resume_path and os.path.exists(resume_path):
                await self._upload_resume(page, resume_path)
            
            # Submit form
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Submit")',
                'button:has-text("Apply")',
                'button:has-text("Send Application")'
            ]
            
            for selector in submit_selectors:
                try:
                    submit_button = await page.wait_for_selector(selector, timeout=2000)
                    if submit_button:
                        await submit_button.click()
                        await page.wait_for_timeout(3000)
                        return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"Error filling generic form: {str(e)}")
            return False
    
    async def _upload_resume(self, page: Page, resume_path: str):
        """Upload resume file"""
        try:
            file_selectors = [
                'input[type="file"]',
                'input[name*="resume"]',
                'input[name*="cv"]',
                'input[id*="resume"]',
                'input[id*="cv"]'
            ]
            
            for selector in file_selectors:
                try:
                    file_input = await page.wait_for_selector(selector, timeout=2000)
                    if file_input:
                        await file_input.set_input_files(resume_path)
                        await self._random_delay(1, 2)
                        break
                except:
                    continue
                    
        except Exception as e:
            logger.error(f"Error uploading resume: {str(e)}")
    
    async def _random_delay(self, min_seconds: float = 1.0, max_seconds: float = 3.0):
        """Add random delay to simulate human behavior"""
        delay = random.uniform(min_seconds, max_seconds)
        await asyncio.sleep(delay)
    
    async def apply_to_jobs_bulk(
        self, 
        jobs: List[Dict[str, Any]], 
        user_profile: Dict[str, Any],
        max_applications: int = 50
    ) -> List[ApplicationResult]:
        """
        Apply to multiple jobs in bulk
        
        Args:
            jobs: List of job dictionaries
            user_profile: User profile information
            max_applications: Maximum number of applications to submit
            
        Returns:
            List of ApplicationResult objects
        """
        results = []
        applied_count = 0
        
        # Shuffle jobs to avoid patterns
        shuffled_jobs = random.sample(jobs, min(len(jobs), max_applications))
        
        for job in shuffled_jobs:
            if applied_count >= max_applications:
                break
                
            try:
                # Random delay between applications
                await self._random_delay(10, 30)
                
                result = await self.apply_to_job(job, user_profile)
                results.append(result)
                
                if result.success:
                    applied_count += 1
                    
                # Additional delay after successful application
                if result.success:
                    await self._random_delay(30, 60)
                    
            except Exception as e:
                logger.error(f"Error in bulk application: {str(e)}")
                results.append(ApplicationResult(
                    job_id=job.get('id', ''),
                    job_url=job.get('job_url', ''),
                    success=False,
                    status='failed',
                    error_message=str(e)
                ))
        
        logger.info(f"Bulk application completed: {applied_count} successful applications out of {len(results)} attempts")
        return results
    
    # Placeholder methods for specific job boards
    async def _apply_glassdoor(self, job_data: Dict[str, Any], user_profile: Dict[str, Any]) -> ApplicationResult:
        """Apply to Glassdoor job - placeholder implementation"""
        return await self._apply_generic(job_data, user_profile)
    
    async def _apply_google(self, job_data: Dict[str, Any], user_profile: Dict[str, Any]) -> ApplicationResult:
        """Apply to Google Jobs - placeholder implementation"""
        return await self._apply_generic(job_data, user_profile)
    
    async def _apply_ziprecruiter(self, job_data: Dict[str, Any], user_profile: Dict[str, Any]) -> ApplicationResult:
        """Apply to ZipRecruiter job - placeholder implementation"""
        return await self._apply_generic(job_data, user_profile)
    
    async def _apply_bayt(self, job_data: Dict[str, Any], user_profile: Dict[str, Any]) -> ApplicationResult:
        """Apply to Bayt job - placeholder implementation"""
        return await self._apply_generic(job_data, user_profile)
    
    async def _apply_naukri(self, job_data: Dict[str, Any], user_profile: Dict[str, Any]) -> ApplicationResult:
        """Apply to Naukri job - placeholder implementation"""
        return await self._apply_generic(job_data, user_profile)
    
    async def _fill_indeed_form(self, page: Page, user_profile: Dict[str, Any]) -> bool:
        """Fill Indeed-specific form - placeholder implementation"""
        return await self._fill_generic_form(page, user_profile)
    
    async def _fill_linkedin_easy_apply(self, page: Page, user_profile: Dict[str, Any]) -> bool:
        """Fill LinkedIn Easy Apply form - placeholder implementation"""
        return await self._fill_generic_form(page, user_profile)

# Example usage
async def test_application_bot():
    """Test the application bot"""
    user_profile = {
        'name': 'John Doe',
        'email': 'john.doe@example.com',
        'phone': '+1234567890',
        'first_name': 'John',
        'last_name': 'Doe',
        'linkedin_url': 'https://linkedin.com/in/johndoe',
        'portfolio_url': 'https://johndoe.dev',
        'cover_letter': 'I am interested in this position...',
        'salary_expectation': '100000',
        'availability': 'Immediately'
    }
    
    job_data = {
        'id': 'test-job-1',
        'job_url': 'https://example.com/job/123',
        'title': 'Software Engineer',
        'company': 'Tech Corp',
        'source': 'indeed'
    }
    
    async with JobApplicationBot(headless=True) as bot:
        result = await bot.apply_to_job(job_data, user_profile)
        print(f"Application result: {result}")

if __name__ == "__main__":
    asyncio.run(test_application_bot())