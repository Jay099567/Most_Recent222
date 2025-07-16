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
import requests
from sentence_transformers import SentenceTransformer
import numpy as np

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
    ai_recommendations: Optional[Dict[str, Any]] = None

class AIJobApplicationBot:
    """
    Advanced AI-powered job application bot with:
    - Multiple job board support
    - AI-powered resume optimization
    - Intelligent form filling
    - Anti-detection measures
    - Success rate optimization
    """
    
    def __init__(self, headless: bool = True, max_retries: int = 3):
        self.headless = headless
        self.max_retries = max_retries
        self.browser = None
        self.context = None
        self.openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
        
        # Initialize AI models
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Advanced user agents for rotation
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0"
        ]
        
        # Job board configurations
        self.job_board_configs = {
            'linkedin': {
                'domain': 'linkedin.com',
                'apply_button_selectors': [
                    '.jobs-apply-button',
                    '.job-actions-apply-button',
                    '.apply-button',
                    '[data-control-name="jobdetails_topcard_inapply"]'
                ],
                'form_selectors': {
                    'first_name': ['input[name="firstName"]', '#firstName'],
                    'last_name': ['input[name="lastName"]', '#lastName'],
                    'email': ['input[name="email"]', '#email'],
                    'phone': ['input[name="phone"]', '#phone'],
                    'resume': ['input[type="file"]', '#resume-upload'],
                    'cover_letter': ['textarea[name="coverLetter"]', '#coverLetter']
                },
                'anti_detection': {
                    'delays': (2, 5),
                    'scroll_behavior': True,
                    'mouse_movements': True
                }
            },
            'indeed': {
                'domain': 'indeed.com',
                'apply_button_selectors': [
                    '.indeedApplyButton',
                    '.indeed-apply-button',
                    '[data-jk]',
                    '.apply-button-container button'
                ],
                'form_selectors': {
                    'first_name': ['input[name="firstName"]', '#applicant.firstName'],
                    'last_name': ['input[name="lastName"]', '#applicant.lastName'],
                    'email': ['input[name="email"]', '#applicant.email'],
                    'phone': ['input[name="phoneNumber"]', '#applicant.phoneNumber'],
                    'resume': ['input[type="file"]', '#resume'],
                    'cover_letter': ['textarea[name="coverLetter"]', '#coverLetter']
                },
                'anti_detection': {
                    'delays': (1, 3),
                    'scroll_behavior': True,
                    'mouse_movements': True
                }
            },
            'glassdoor': {
                'domain': 'glassdoor.com',
                'apply_button_selectors': [
                    '.apply-btn',
                    '.apply-button',
                    '[data-test="apply-button"]'
                ],
                'form_selectors': {
                    'first_name': ['input[name="firstName"]', '#firstName'],
                    'last_name': ['input[name="lastName"]', '#lastName'],
                    'email': ['input[name="email"]', '#email'],
                    'phone': ['input[name="phone"]', '#phone'],
                    'resume': ['input[type="file"]', '#resume'],
                    'cover_letter': ['textarea[name="coverLetter"]', '#coverLetter']
                },
                'anti_detection': {
                    'delays': (2, 4),
                    'scroll_behavior': True,
                    'mouse_movements': True
                }
            },
            'ziprecruiter': {
                'domain': 'ziprecruiter.com',
                'apply_button_selectors': [
                    '.apply_button',
                    '.apply-button',
                    '[data-testid="apply-button"]'
                ],
                'form_selectors': {
                    'first_name': ['input[name="firstName"]', '#firstName'],
                    'last_name': ['input[name="lastName"]', '#lastName'],
                    'email': ['input[name="email"]', '#email'],
                    'phone': ['input[name="phone"]', '#phone'],
                    'resume': ['input[type="file"]', '#resume'],
                    'cover_letter': ['textarea[name="coverLetter"]', '#coverLetter']
                },
                'anti_detection': {
                    'delays': (1, 3),
                    'scroll_behavior': True,
                    'mouse_movements': True
                }
            },
            'monster': {
                'domain': 'monster.com',
                'apply_button_selectors': [
                    '.apply-button',
                    '.btn-apply',
                    '[data-testid="apply-button"]'
                ],
                'form_selectors': {
                    'first_name': ['input[name="firstName"]', '#firstName'],
                    'last_name': ['input[name="lastName"]', '#lastName'],
                    'email': ['input[name="email"]', '#email'],
                    'phone': ['input[name="phone"]', '#phone'],
                    'resume': ['input[type="file"]', '#resume'],
                    'cover_letter': ['textarea[name="coverLetter"]', '#coverLetter']
                },
                'anti_detection': {
                    'delays': (2, 4),
                    'scroll_behavior': True,
                    'mouse_movements': True
                }
            },
            'careerbuilder': {
                'domain': 'careerbuilder.com',
                'apply_button_selectors': [
                    '.apply-button',
                    '.btn-apply',
                    '[data-testid="apply-button"]'
                ],
                'form_selectors': {
                    'first_name': ['input[name="firstName"]', '#firstName'],
                    'last_name': ['input[name="lastName"]', '#lastName'],
                    'email': ['input[name="email"]', '#email'],
                    'phone': ['input[name="phone"]', '#phone'],
                    'resume': ['input[type="file"]', '#resume'],
                    'cover_letter': ['textarea[name="coverLetter"]', '#coverLetter']
                },
                'anti_detection': {
                    'delays': (2, 5),
                    'scroll_behavior': True,
                    'mouse_movements': True
                }
            }
        }
        
    async def initialize_browser(self) -> None:
        """Initialize browser with advanced anti-detection measures"""
        try:
            self.playwright = await async_playwright().start()
            
            # Advanced browser launch options
            launch_options = {
                'headless': self.headless,
                'args': [
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--disable-accelerated-jpeg-decoding',
                    '--disable-accelerated-mjpeg-decode',
                    '--disable-accelerated-video-decode',
                    '--disable-accelerated-video-encode',
                    '--disable-app-list-dismiss-on-blur',
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-client-side-phishing-detection',
                    '--disable-default-apps',
                    '--disable-dev-shm-usage',
                    '--disable-extensions',
                    '--disable-features=TranslateUI',
                    '--disable-hang-monitor',
                    '--disable-ipc-flooding-protection',
                    '--disable-popup-blocking',
                    '--disable-prompt-on-repost',
                    '--disable-renderer-backgrounding',
                    '--disable-sync',
                    '--disable-web-security',
                    '--enable-features=NetworkService',
                    '--force-color-profile=srgb',
                    '--metrics-recording-only',
                    '--no-first-run',
                    '--password-store=basic',
                    '--use-mock-keychain',
                    '--user-agent=' + random.choice(self.user_agents)
                ]
            }
            
            self.browser = await self.playwright.chromium.launch(**launch_options)
            
            # Create context with stealth settings
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=random.choice(self.user_agents),
                locale='en-US',
                timezone_id='America/New_York',
                permissions=['geolocation'],
                geolocation={'latitude': 40.7128, 'longitude': -74.0060}
            )
            
            # Add stealth scripts
            await self.context.add_init_script("""
                // Pass webdriver check
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });
                
                // Pass chrome check
                window.chrome = {
                    runtime: {},
                };
                
                // Pass permissions check
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """)
            
            logger.info("Browser initialized with anti-detection measures")
            
        except Exception as e:
            logger.error(f"Failed to initialize browser: {str(e)}")
            raise
    
    async def ai_optimize_resume(self, resume_text: str, job_description: str) -> str:
        """
        Use AI to optimize resume for specific job
        """
        try:
            prompt = f"""
            You are an expert resume optimizer. Given the following resume and job description, 
            optimize the resume to better match the job requirements while maintaining authenticity.
            
            RESUME:
            {resume_text}
            
            JOB DESCRIPTION:
            {job_description}
            
            Please provide an optimized resume that:
            1. Highlights relevant skills and experience
            2. Uses keywords from the job description
            3. Maintains professional formatting
            4. Stays truthful and authentic
            
            Return only the optimized resume text:
            """
            
            headers = {
                'Authorization': f'Bearer {self.openrouter_api_key}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'model': 'anthropic/claude-3.5-sonnet',
                'messages': [
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ],
                'max_tokens': 4000,
                'temperature': 0.3
            }
            
            response = requests.post(
                'https://openrouter.ai/api/v1/chat/completions',
                headers=headers,
                json=data
            )
            
            if response.status_code == 200:
                result = response.json()
                optimized_resume = result['choices'][0]['message']['content']
                logger.info("Resume optimized successfully with AI")
                return optimized_resume
            else:
                logger.error(f"AI optimization failed: {response.status_code}")
                return resume_text
                
        except Exception as e:
            logger.error(f"AI resume optimization failed: {str(e)}")
            return resume_text
    
    async def ai_generate_cover_letter(self, resume_text: str, job_description: str, company_name: str) -> str:
        """
        Generate AI-powered cover letter
        """
        try:
            prompt = f"""
            You are an expert cover letter writer. Create a compelling, professional cover letter 
            for the following job application:
            
            RESUME:
            {resume_text}
            
            JOB DESCRIPTION:
            {job_description}
            
            COMPANY NAME:
            {company_name}
            
            Please create a cover letter that:
            1. Is personalized for the specific role and company
            2. Highlights relevant experience and skills
            3. Shows enthusiasm for the position
            4. Is concise and professional (max 400 words)
            5. Has a strong opening and closing
            
            Return only the cover letter text:
            """
            
            headers = {
                'Authorization': f'Bearer {self.openrouter_api_key}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'model': 'anthropic/claude-3.5-sonnet',
                'messages': [
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ],
                'max_tokens': 1000,
                'temperature': 0.4
            }
            
            response = requests.post(
                'https://openrouter.ai/api/v1/chat/completions',
                headers=headers,
                json=data
            )
            
            if response.status_code == 200:
                result = response.json()
                cover_letter = result['choices'][0]['message']['content']
                logger.info("Cover letter generated successfully with AI")
                return cover_letter
            else:
                logger.error(f"AI cover letter generation failed: {response.status_code}")
                return ""
                
        except Exception as e:
            logger.error(f"AI cover letter generation failed: {str(e)}")
            return ""
    
    async def intelligent_form_fill(self, page: Page, form_data: Dict[str, Any], job_board: str) -> bool:
        """
        Intelligently fill application forms based on job board
        """
        try:
            config = self.job_board_configs.get(job_board, {})
            form_selectors = config.get('form_selectors', {})
            anti_detection = config.get('anti_detection', {})
            
            # Human-like delays
            delay_range = anti_detection.get('delays', (1, 3))
            
            # Fill form fields
            for field_name, value in form_data.items():
                if field_name in form_selectors:
                    selectors = form_selectors[field_name]
                    
                    for selector in selectors:
                        try:
                            element = await page.wait_for_selector(selector, timeout=5000)
                            if element:
                                # Human-like typing
                                await element.clear()
                                await element.type(str(value), delay=random.randint(50, 150))
                                await asyncio.sleep(random.uniform(*delay_range))
                                logger.info(f"Filled field: {field_name}")
                                break
                        except Exception as e:
                            logger.debug(f"Selector {selector} not found for {field_name}: {e}")
                            continue
            
            # Human-like mouse movements and scrolling
            if anti_detection.get('mouse_movements'):
                await self.simulate_human_behavior(page)
            
            return True
            
        except Exception as e:
            logger.error(f"Form filling failed: {str(e)}")
            return False
    
    async def simulate_human_behavior(self, page: Page) -> None:
        """
        Simulate human-like behavior to avoid detection
        """
        try:
            # Random mouse movements
            for _ in range(random.randint(2, 5)):
                x = random.randint(100, 800)
                y = random.randint(100, 600)
                await page.mouse.move(x, y)
                await asyncio.sleep(random.uniform(0.1, 0.3))
            
            # Random scrolling
            for _ in range(random.randint(1, 3)):
                await page.mouse.wheel(0, random.randint(-200, 200))
                await asyncio.sleep(random.uniform(0.5, 1.0))
            
            # Random clicks in safe areas
            await page.mouse.click(random.randint(50, 100), random.randint(50, 100))
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
        except Exception as e:
            logger.debug(f"Human behavior simulation failed: {e}")
    
    async def detect_job_board(self, url: str) -> str:
        """
        Detect which job board the URL belongs to
        """
        domain = urlparse(url).netloc.lower()
        
        for board_name, config in self.job_board_configs.items():
            if config['domain'] in domain:
                return board_name
        
        return 'generic'
    
    async def apply_to_job(self, job_url: str, user_data: Dict[str, Any]) -> ApplicationResult:
        """
        Apply to a job using AI-powered optimization
        """
        job_id = user_data.get('job_id', str(hash(job_url)))
        
        try:
            # Initialize browser if not already done
            if not self.browser:
                await self.initialize_browser()
            
            # Create new page
            page = await self.context.new_page()
            
            # Detect job board
            job_board = await self.detect_job_board(job_url)
            logger.info(f"Detected job board: {job_board}")
            
            # Navigate to job page
            await page.goto(job_url, wait_until='networkidle')
            await asyncio.sleep(random.uniform(2, 4))
            
            # Extract job description for AI optimization
            job_description = await self.extract_job_description(page)
            company_name = await self.extract_company_name(page)
            
            # AI-optimize resume for this specific job
            optimized_resume = await self.ai_optimize_resume(
                user_data.get('resume_text', ''), 
                job_description
            )
            
            # Generate AI cover letter
            cover_letter = await self.ai_generate_cover_letter(
                optimized_resume, 
                job_description, 
                company_name
            )
            
            # Find and click apply button
            apply_clicked = await self.find_and_click_apply_button(page, job_board)
            
            if not apply_clicked:
                return ApplicationResult(
                    job_id=job_id,
                    job_url=job_url,
                    success=False,
                    status='failed',
                    error_message='Apply button not found'
                )
            
            # Wait for application form
            await asyncio.sleep(random.uniform(3, 6))
            
            # Prepare form data with AI-optimized content
            form_data = {
                'first_name': user_data.get('first_name', ''),
                'last_name': user_data.get('last_name', ''),
                'email': user_data.get('email', ''),
                'phone': user_data.get('phone', ''),
                'resume': optimized_resume,
                'cover_letter': cover_letter
            }
            
            # Fill form intelligently
            form_filled = await self.intelligent_form_fill(page, form_data, job_board)
            
            if not form_filled:
                return ApplicationResult(
                    job_id=job_id,
                    job_url=job_url,
                    success=False,
                    status='failed',
                    error_message='Form filling failed'
                )
            
            # Submit application
            submit_success = await self.submit_application(page, job_board)
            
            if submit_success:
                return ApplicationResult(
                    job_id=job_id,
                    job_url=job_url,
                    success=True,
                    status='applied',
                    applied_at=datetime.utcnow(),
                    ai_recommendations={
                        'resume_optimized': True,
                        'cover_letter_generated': True,
                        'job_board': job_board,
                        'company_name': company_name
                    }
                )
            else:
                return ApplicationResult(
                    job_id=job_id,
                    job_url=job_url,
                    success=False,
                    status='failed',
                    error_message='Application submission failed'
                )
                
        except Exception as e:
            logger.error(f"Application failed for {job_url}: {str(e)}")
            return ApplicationResult(
                job_id=job_id,
                job_url=job_url,
                success=False,
                status='failed',
                error_message=str(e)
            )
        finally:
            if 'page' in locals():
                await page.close()
    
    async def extract_job_description(self, page: Page) -> str:
        """
        Extract job description from the page
        """
        try:
            # Common selectors for job descriptions
            selectors = [
                '.job-description',
                '.job-details',
                '.job-summary',
                '.description',
                '[data-testid="job-description"]',
                '.job-view-description'
            ]
            
            for selector in selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=3000)
                    if element:
                        description = await element.text_content()
                        return description.strip()
                except:
                    continue
            
            # Fallback: get all text content
            body_text = await page.text_content('body')
            return body_text[:2000]  # Limit to first 2000 chars
            
        except Exception as e:
            logger.error(f"Failed to extract job description: {e}")
            return "Job description not available"
    
    async def extract_company_name(self, page: Page) -> str:
        """
        Extract company name from the page
        """
        try:
            # Common selectors for company names
            selectors = [
                '.company-name',
                '.employer-name',
                '.company',
                '[data-testid="company-name"]',
                '.job-company'
            ]
            
            for selector in selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=3000)
                    if element:
                        company = await element.text_content()
                        return company.strip()
                except:
                    continue
            
            return "Company"
            
        except Exception as e:
            logger.error(f"Failed to extract company name: {e}")
            return "Company"
    
    async def find_and_click_apply_button(self, page: Page, job_board: str) -> bool:
        """
        Find and click the apply button for specific job board
        """
        try:
            config = self.job_board_configs.get(job_board, {})
            selectors = config.get('apply_button_selectors', ['.apply-button'])
            
            for selector in selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=5000)
                    if element:
                        # Check if button is visible and clickable
                        is_visible = await element.is_visible()
                        is_enabled = await element.is_enabled()
                        
                        if is_visible and is_enabled:
                            await element.click()
                            logger.info(f"Apply button clicked: {selector}")
                            return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to find apply button: {e}")
            return False
    
    async def submit_application(self, page: Page, job_board: str) -> bool:
        """
        Submit the application form
        """
        try:
            # Common submit button selectors
            submit_selectors = [
                'button[type="submit"]',
                '.submit-button',
                '.apply-submit',
                '[data-testid="submit-application"]',
                '.btn-primary',
                '.submit-btn'
            ]
            
            for selector in submit_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=5000)
                    if element:
                        is_visible = await element.is_visible()
                        is_enabled = await element.is_enabled()
                        
                        if is_visible and is_enabled:
                            await element.click()
                            logger.info(f"Application submitted: {selector}")
                            
                            # Wait for confirmation
                            await asyncio.sleep(3)
                            return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to submit application: {e}")
            return False
    
    async def apply_to_multiple_jobs(self, job_urls: List[str], user_data: Dict[str, Any]) -> List[ApplicationResult]:
        """
        Apply to multiple jobs with AI optimization
        """
        results = []
        
        for i, job_url in enumerate(job_urls):
            try:
                logger.info(f"Applying to job {i+1}/{len(job_urls)}: {job_url}")
                
                # Add job index to user data
                user_data['job_id'] = f"job_{i+1}_{hash(job_url)}"
                
                # Apply to job
                result = await self.apply_to_job(job_url, user_data)
                results.append(result)
                
                # Random delay between applications
                await asyncio.sleep(random.uniform(10, 30))
                
            except Exception as e:
                logger.error(f"Failed to apply to {job_url}: {str(e)}")
                results.append(ApplicationResult(
                    job_id=f"job_{i+1}_{hash(job_url)}",
                    job_url=job_url,
                    success=False,
                    status='failed',
                    error_message=str(e)
                ))
        
        return results
    
    async def close(self) -> None:
        """
        Close browser and cleanup
        """
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if hasattr(self, 'playwright'):
                await self.playwright.stop()
            logger.info("Browser closed successfully")
        except Exception as e:
            logger.error(f"Error closing browser: {e}")

# Usage example
async def main():
    """
    Example usage of the AI Job Application Bot
    """
    user_data = {
        'first_name': 'John',
        'last_name': 'Doe',
        'email': 'john.doe@example.com',
        'phone': '+1234567890',
        'resume_text': 'Experienced software engineer with 5+ years in Python, JavaScript, and React...'
    }
    
    job_urls = [
        'https://www.linkedin.com/jobs/view/12345',
        'https://www.indeed.com/viewjob?jk=abcdef',
        'https://www.glassdoor.com/job-listing/software-engineer-xyz-corp-JV_IC123456_KO0,17_KE18,26.htm'
    ]
    
    bot = AIJobApplicationBot(headless=True)
    
    try:
        results = await bot.apply_to_multiple_jobs(job_urls, user_data)
        
        for result in results:
            print(f"Job: {result.job_url}")
            print(f"Success: {result.success}")
            print(f"Status: {result.status}")
            if result.ai_recommendations:
                print(f"AI Recommendations: {result.ai_recommendations}")
            print("-" * 50)
            
    finally:
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())