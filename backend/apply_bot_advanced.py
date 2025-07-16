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
import base64
import hashlib
from pathlib import Path

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
    status: str  # 'applied', 'failed', 'requires_manual', 'already_applied', 'not_supported'
    error_message: Optional[str] = None
    application_id: Optional[str] = None
    screenshot_path: Optional[str] = None
    retry_count: int = 0
    applied_at: datetime = None
    application_method: str = "unknown"  # 'easy_apply', 'external', 'direct'
    confidence_score: float = 0.0  # How confident we are in the application success

class AdvancedJobApplicationBot:
    """
    Advanced autonomous job application bot with enhanced capabilities
    - Multi-platform support with platform-specific strategies
    - Smart form detection and filling
    - CAPTCHA handling and human-like behavior
    - Advanced anti-detection measures
    - Resume optimization per job
    """
    
    def __init__(self, headless: bool = True, max_retries: int = 3, stealth_mode: bool = True):
        self.headless = headless
        self.max_retries = max_retries
        self.stealth_mode = stealth_mode
        self.browser = None
        self.context = None
        self.screenshots_dir = Path("./screenshots")
        self.screenshots_dir.mkdir(exist_ok=True)
        
        # Enhanced user agents with more variety
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
        ]
        
        # Advanced application strategies per platform
        self.application_strategies = {
            'indeed': self._apply_indeed_advanced,
            'linkedin': self._apply_linkedin_advanced,
            'glassdoor': self._apply_glassdoor_advanced,
            'google': self._apply_google_advanced,
            'zip_recruiter': self._apply_ziprecruiter_advanced,
            'bayt': self._apply_bayt_advanced,
            'naukri': self._apply_naukri_advanced,
            'lever': self._apply_lever_advanced,
            'greenhouse': self._apply_greenhouse_advanced,
            'workday': self._apply_workday_advanced,
            'bamboohr': self._apply_bamboohr_advanced,
            'smartrecruiters': self._apply_smartrecruiters_advanced
        }
        
        # Smart form field detection patterns
        self.smart_field_patterns = {
            'email': {
                'selectors': ['input[type="email"]', 'input[name*="email"]', 'input[id*="email"]', 'input[placeholder*="email"]'],
                'keywords': ['email', 'e-mail', 'mail', 'contact']
            },
            'phone': {
                'selectors': ['input[type="tel"]', 'input[name*="phone"]', 'input[id*="phone"]', 'input[placeholder*="phone"]'],
                'keywords': ['phone', 'mobile', 'tel', 'contact', 'number']
            },
            'first_name': {
                'selectors': ['input[name*="first"]', 'input[id*="first"]', 'input[placeholder*="first"]'],
                'keywords': ['first', 'given', 'fname']
            },
            'last_name': {
                'selectors': ['input[name*="last"]', 'input[id*="last"]', 'input[placeholder*="last"]'],
                'keywords': ['last', 'family', 'surname', 'lname']
            },
            'full_name': {
                'selectors': ['input[name*="name"]', 'input[id*="name"]', 'input[placeholder*="name"]'],
                'keywords': ['name', 'full', 'complete']
            },
            'resume': {
                'selectors': ['input[type="file"]', 'input[name*="resume"]', 'input[id*="resume"]', 'input[name*="cv"]'],
                'keywords': ['resume', 'cv', 'file', 'upload', 'attach']
            },
            'cover_letter': {
                'selectors': ['textarea[name*="cover"]', 'textarea[id*="cover"]', 'textarea[placeholder*="cover"]'],
                'keywords': ['cover', 'letter', 'message', 'intro']
            },
            'linkedin_url': {
                'selectors': ['input[name*="linkedin"]', 'input[id*="linkedin"]', 'input[placeholder*="linkedin"]'],
                'keywords': ['linkedin', 'profile', 'social']
            },
            'portfolio_url': {
                'selectors': ['input[name*="portfolio"]', 'input[id*="portfolio"]', 'input[placeholder*="portfolio"]'],
                'keywords': ['portfolio', 'website', 'url', 'link']
            },
            'salary_expectation': {
                'selectors': ['input[name*="salary"]', 'input[id*="salary"]', 'input[placeholder*="salary"]'],
                'keywords': ['salary', 'compensation', 'pay', 'wage']
            },
            'availability': {
                'selectors': ['input[name*="start"]', 'input[id*="start"]', 'select[name*="availability"]'],
                'keywords': ['start', 'available', 'notice', 'when']
            }
        }
        
        # Success indicators for different platforms
        self.success_indicators = {
            'indeed': ['application submitted', 'application sent', 'thank you', 'confirmation'],
            'linkedin': ['application submitted', 'your application has been sent', 'thanks for applying'],
            'glassdoor': ['application submitted', 'application sent', 'thank you'],
            'google': ['application submitted', 'application sent'],
            'zip_recruiter': ['application submitted', 'application sent'],
            'generic': ['success', 'submitted', 'sent', 'thank you', 'confirmation', 'applied']
        }
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self.start_browser()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close_browser()
        
    async def start_browser(self):
        """Start enhanced browser with advanced stealth settings"""
        try:
            self.playwright = await async_playwright().start()
            
            # Advanced browser launch arguments
            launch_args = [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--disable-gpu',
                '--window-size=1920,1080',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor',
                '--disable-blink-features=AutomationControlled',
                '--disable-extensions',
                '--disable-plugins',
                '--disable-images',  # Faster loading
                '--disable-javascript-harmony-shipping',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding',
                '--disable-field-trial-config',
                '--disable-back-forward-cache',
                '--disable-ipc-flooding-protection',
                '--no-first-run',
                '--no-default-browser-check',
                '--no-pings',
                '--no-zygote',
                '--single-process'
            ]
            
            # Launch browser with enhanced settings
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=launch_args,
                slow_mo=random.randint(50, 150) if self.stealth_mode else 0
            )
            
            # Create context with enhanced stealth
            self.context = await self.browser.new_context(
                user_agent=random.choice(self.user_agents),
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                timezone_id='America/New_York',
                permissions=['geolocation'],
                geolocation={'longitude': -74.0060, 'latitude': 40.7128},  # New York
                accept_downloads=True,
                ignore_https_errors=True,
                java_script_enabled=True,
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
            )
            
            # Add advanced stealth scripts
            await self.context.add_init_script("""
                // Remove webdriver property
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });
                
                // Mock languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                });
                
                // Mock plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                
                // Mock chrome object
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                    app: {}
                };
                
                // Mock permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                
                // Mock webgl
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    if (parameter === 37445) {
                        return 'Intel Inc.';
                    }
                    if (parameter === 37446) {
                        return 'Intel Iris OpenGL Engine';
                    }
                    return getParameter(parameter);
                };
                
                // Add random mouse movements
                document.addEventListener('DOMContentLoaded', function() {
                    setInterval(() => {
                        const event = new MouseEvent('mousemove', {
                            bubbles: true,
                            cancelable: true,
                            clientX: Math.random() * window.innerWidth,
                            clientY: Math.random() * window.innerHeight
                        });
                        document.dispatchEvent(event);
                    }, Math.random() * 5000 + 1000);
                });
            """)
            
            logger.info("Advanced browser started successfully with stealth mode")
            
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
        Apply to a single job with enhanced capabilities
        
        Args:
            job_data: Job information including URL, title, company, etc.
            user_profile: User profile with personal info and preferences
            
        Returns:
            ApplicationResult object with application status
        """
        job_url = job_data.get('job_url', '')
        job_id = job_data.get('id', '')
        source = job_data.get('source', '').lower()
        
        logger.info(f"🎯 Applying to: {job_data.get('title', '')} at {job_data.get('company', '')}")
        logger.info(f"📍 Source: {source}, URL: {job_url}")
        
        # Determine application strategy
        strategy = self.application_strategies.get(source, self._apply_generic_advanced)
        
        # Apply with enhanced retry logic
        for attempt in range(self.max_retries + 1):
            try:
                logger.info(f"🔄 Attempt {attempt + 1} of {self.max_retries + 1}")
                
                result = await strategy(job_data, user_profile)
                result.retry_count = attempt
                
                if result.success:
                    logger.info(f"✅ Successfully applied to job {job_id}")
                    return result
                elif result.status in ['already_applied', 'not_supported']:
                    logger.info(f"ℹ️ Job {job_id}: {result.status}")
                    return result
                    
            except Exception as e:
                logger.error(f"❌ Attempt {attempt + 1} failed for job {job_id}: {str(e)}")
                if attempt < self.max_retries:
                    delay = random.uniform(3, 8) * (attempt + 1)
                    await asyncio.sleep(delay)
                else:
                    return ApplicationResult(
                        job_id=job_id,
                        job_url=job_url,
                        success=False,
                        status='failed',
                        error_message=str(e),
                        retry_count=attempt,
                        confidence_score=0.0
                    )
        
        return ApplicationResult(
            job_id=job_id,
            job_url=job_url,
            success=False,
            status='failed',
            error_message='Max retries exceeded',
            retry_count=self.max_retries,
            confidence_score=0.0
        )
    
    async def _apply_indeed_advanced(self, job_data: Dict[str, Any], user_profile: Dict[str, Any]) -> ApplicationResult:
        """Advanced Indeed application with enhanced detection"""
        page = await self.context.new_page()
        job_url = job_data['job_url']
        job_id = job_data['id']
        
        try:
            # Navigate with enhanced stealth
            await page.goto(job_url, wait_until='networkidle', timeout=30000)
            await self._human_like_delay(2, 4)
            
            # Take screenshot for debugging
            screenshot_path = await self._take_screenshot(page, f"indeed_{job_id}_initial")
            
            # Enhanced apply button detection
            apply_selectors = [
                'button[aria-label*="Apply"]',
                'button:has-text("Apply now")',
                'button:has-text("Apply")',
                'a:has-text("Apply now")',
                'a:has-text("Apply")',
                '[data-testid="apply-button"]',
                '.jobsearch-ApplyButton',
                '.jobsearch-SerpJobCard-footer button',
                '.jobsearch-JobComponent-footer button'
            ]
            
            apply_button = await self._find_element_smart(page, apply_selectors)
            if not apply_button:
                return ApplicationResult(
                    job_id=job_id,
                    job_url=job_url,
                    success=False,
                    status='failed',
                    error_message='Apply button not found',
                    screenshot_path=screenshot_path,
                    confidence_score=0.0
                )
            
            # Click apply button with human-like behavior
            await self._human_like_click(apply_button)
            await page.wait_for_timeout(3000)
            
            # Check if it's an Indeed Easy Apply or external redirect
            current_url = page.url
            if 'indeed.com' in current_url:
                # Indeed native application
                result = await self._fill_indeed_form_advanced(page, user_profile)
                application_method = "easy_apply"
            else:
                # External application
                result = await self._fill_generic_form_advanced(page, user_profile)
                application_method = "external"
            
            # Enhanced success detection
            success_detected = await self._detect_application_success(page, 'indeed')
            
            if result or success_detected:
                screenshot_path = await self._take_screenshot(page, f"indeed_{job_id}_success")
                return ApplicationResult(
                    job_id=job_id,
                    job_url=job_url,
                    success=True,
                    status='applied',
                    applied_at=datetime.utcnow(),
                    application_method=application_method,
                    screenshot_path=screenshot_path,
                    confidence_score=0.9 if success_detected else 0.7
                )
            
            return ApplicationResult(
                job_id=job_id,
                job_url=job_url,
                success=False,
                status='failed',
                error_message='Form submission failed',
                screenshot_path=screenshot_path,
                confidence_score=0.0
            )
            
        except Exception as e:
            logger.error(f"Error applying to Indeed job: {str(e)}")
            screenshot_path = await self._take_screenshot(page, f"indeed_{job_id}_error")
            return ApplicationResult(
                job_id=job_id,
                job_url=job_url,
                success=False,
                status='failed',
                error_message=str(e),
                screenshot_path=screenshot_path,
                confidence_score=0.0
            )
        finally:
            await page.close()
    
    async def _apply_linkedin_advanced(self, job_data: Dict[str, Any], user_profile: Dict[str, Any]) -> ApplicationResult:
        """Advanced LinkedIn application with Easy Apply detection"""
        page = await self.context.new_page()
        job_url = job_data['job_url']
        job_id = job_data['id']
        
        try:
            # Navigate to LinkedIn job
            await page.goto(job_url, wait_until='networkidle', timeout=30000)
            await self._human_like_delay(2, 4)
            
            # Enhanced Easy Apply detection
            easy_apply_selectors = [
                'button[aria-label*="Easy Apply"]',
                'button:has-text("Easy Apply")',
                '.jobs-apply-button',
                '.jobs-s-apply button',
                '[data-control-name="jobdetails_topcard_inapply"]'
            ]
            
            easy_apply_button = await self._find_element_smart(page, easy_apply_selectors)
            if not easy_apply_button:
                return ApplicationResult(
                    job_id=job_id,
                    job_url=job_url,
                    success=False,
                    status='not_supported',
                    error_message='Easy Apply not available',
                    confidence_score=0.0
                )
            
            # Click Easy Apply
            await self._human_like_click(easy_apply_button)
            await page.wait_for_timeout(3000)
            
            # Handle LinkedIn Easy Apply multi-step process
            result = await self._fill_linkedin_easy_apply_advanced(page, user_profile)
            
            if result:
                screenshot_path = await self._take_screenshot(page, f"linkedin_{job_id}_success")
                return ApplicationResult(
                    job_id=job_id,
                    job_url=job_url,
                    success=True,
                    status='applied',
                    applied_at=datetime.utcnow(),
                    application_method="easy_apply",
                    screenshot_path=screenshot_path,
                    confidence_score=0.9
                )
            
            return ApplicationResult(
                job_id=job_id,
                job_url=job_url,
                success=False,
                status='failed',
                error_message='LinkedIn Easy Apply failed',
                confidence_score=0.0
            )
            
        except Exception as e:
            logger.error(f"Error applying to LinkedIn job: {str(e)}")
            return ApplicationResult(
                job_id=job_id,
                job_url=job_url,
                success=False,
                status='failed',
                error_message=str(e),
                confidence_score=0.0
            )
        finally:
            await page.close()
    
    async def _apply_generic_advanced(self, job_data: Dict[str, Any], user_profile: Dict[str, Any]) -> ApplicationResult:
        """Advanced generic application with smart form detection"""
        page = await self.context.new_page()
        job_url = job_data['job_url']
        job_id = job_data['id']
        
        try:
            # Navigate to job page
            await page.goto(job_url, wait_until='networkidle', timeout=30000)
            await self._human_like_delay(2, 4)
            
            # Enhanced apply button detection
            apply_selectors = [
                'button[class*="apply"]',
                'button:has-text("Apply")',
                'a:has-text("Apply")',
                'button:has-text("Submit Application")',
                'input[type="submit"][value*="Apply"]',
                '.apply-button',
                '#apply-button',
                '[data-testid*="apply"]',
                '[data-test*="apply"]'
            ]
            
            apply_button = await self._find_element_smart(page, apply_selectors)
            if not apply_button:
                return ApplicationResult(
                    job_id=job_id,
                    job_url=job_url,
                    success=False,
                    status='failed',
                    error_message='Apply button not found',
                    confidence_score=0.0
                )
            
            # Click apply button
            await self._human_like_click(apply_button)
            await page.wait_for_timeout(3000)
            
            # Fill advanced form
            result = await self._fill_generic_form_advanced(page, user_profile)
            
            if result:
                success_detected = await self._detect_application_success(page, 'generic')
                confidence = 0.9 if success_detected else 0.6
                
                return ApplicationResult(
                    job_id=job_id,
                    job_url=job_url,
                    success=True,
                    status='applied',
                    applied_at=datetime.utcnow(),
                    application_method="direct",
                    confidence_score=confidence
                )
            
            return ApplicationResult(
                job_id=job_id,
                job_url=job_url,
                success=False,
                status='failed',
                error_message='Generic form submission failed',
                confidence_score=0.0
            )
            
        except Exception as e:
            logger.error(f"Error applying to generic job: {str(e)}")
            return ApplicationResult(
                job_id=job_id,
                job_url=job_url,
                success=False,
                status='failed',
                error_message=str(e),
                confidence_score=0.0
            )
        finally:
            await page.close()
    
    async def _fill_generic_form_advanced(self, page: Page, user_profile: Dict[str, Any]) -> bool:
        """Advanced generic form filling with smart field detection"""
        try:
            # Prepare form data
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
            
            # Smart form field detection and filling
            for field_type, field_config in self.smart_field_patterns.items():
                value = form_data.get(field_type, '')
                if value:
                    field_found = await self._find_and_fill_field(page, field_config, value)
                    if field_found:
                        logger.info(f"✅ Filled {field_type} field")
                        await self._human_like_delay(0.5, 1.5)
            
            # Handle file uploads (resume)
            resume_path = user_profile.get('resume_path')
            if resume_path and os.path.exists(resume_path):
                await self._upload_resume_advanced(page, resume_path)
            
            # Handle dropdowns and select fields
            await self._handle_dropdown_fields(page, user_profile)
            
            # Handle checkboxes and radio buttons
            await self._handle_checkbox_fields(page, user_profile)
            
            # Submit form with enhanced detection
            return await self._submit_form_advanced(page)
            
        except Exception as e:
            logger.error(f"Error filling advanced form: {str(e)}")
            return False
    
    async def _find_and_fill_field(self, page: Page, field_config: Dict, value: str) -> bool:
        """Smart field detection and filling"""
        try:
            # Try direct selectors first
            for selector in field_config['selectors']:
                try:
                    field = await page.wait_for_selector(selector, timeout=2000)
                    if field:
                        await field.clear()
                        await field.type(value, delay=random.randint(50, 150))
                        return True
                except:
                    continue
            
            # Try keyword-based detection
            for keyword in field_config['keywords']:
                selectors = [
                    f'input[name*="{keyword}"]',
                    f'input[id*="{keyword}"]',
                    f'input[placeholder*="{keyword}"]',
                    f'textarea[name*="{keyword}"]',
                    f'textarea[id*="{keyword}"]',
                    f'textarea[placeholder*="{keyword}"]'
                ]
                
                for selector in selectors:
                    try:
                        field = await page.wait_for_selector(selector, timeout=1000)
                        if field:
                            await field.clear()
                            await field.type(value, delay=random.randint(50, 150))
                            return True
                    except:
                        continue
            
            return False
            
        except Exception as e:
            logger.error(f"Error finding and filling field: {str(e)}")
            return False
    
    async def _upload_resume_advanced(self, page: Page, resume_path: str):
        """Advanced resume upload with multiple strategies"""
        try:
            file_selectors = [
                'input[type="file"]',
                'input[name*="resume"]',
                'input[name*="cv"]',
                'input[id*="resume"]',
                'input[id*="cv"]',
                'input[accept*=".pdf"]',
                'input[accept*=".doc"]'
            ]
            
            for selector in file_selectors:
                try:
                    file_input = await page.wait_for_selector(selector, timeout=2000)
                    if file_input:
                        await file_input.set_input_files(resume_path)
                        await self._human_like_delay(2, 4)
                        logger.info("✅ Resume uploaded successfully")
                        return True
                except:
                    continue
            
            # Try drag and drop upload
            await self._try_drag_drop_upload(page, resume_path)
            
        except Exception as e:
            logger.error(f"Error uploading resume: {str(e)}")
    
    async def _submit_form_advanced(self, page: Page) -> bool:
        """Advanced form submission with multiple strategies"""
        try:
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Submit")',
                'button:has-text("Apply")',
                'button:has-text("Send Application")',
                'button:has-text("Send")',
                '.submit-button',
                '.apply-button',
                '#submit-button',
                '#apply-button'
            ]
            
            for selector in submit_selectors:
                try:
                    submit_button = await page.wait_for_selector(selector, timeout=2000)
                    if submit_button:
                        await self._human_like_click(submit_button)
                        await page.wait_for_timeout(3000)
                        logger.info("✅ Form submitted successfully")
                        return True
                except:
                    continue
            
            # Try Enter key submission
            try:
                await page.keyboard.press('Enter')
                await page.wait_for_timeout(3000)
                logger.info("✅ Form submitted via Enter key")
                return True
            except:
                pass
            
            return False
            
        except Exception as e:
            logger.error(f"Error submitting form: {str(e)}")
            return False
    
    async def _detect_application_success(self, page: Page, platform: str) -> bool:
        """Enhanced success detection with multiple indicators"""
        try:
            # Wait for page to load after submission
            await page.wait_for_timeout(3000)
            
            # Get success indicators for platform
            indicators = self.success_indicators.get(platform, self.success_indicators['generic'])
            
            # Check page content for success indicators
            page_content = await page.content()
            page_text = await page.text_content('body')
            
            for indicator in indicators:
                if indicator.lower() in page_text.lower():
                    logger.info(f"✅ Success indicator found: {indicator}")
                    return True
            
            # Check for success-related selectors
            success_selectors = [
                '.success',
                '.confirmation',
                '.thank-you',
                '.submitted',
                '[class*="success"]',
                '[class*="confirmation"]',
                '[class*="thank"]'
            ]
            
            for selector in success_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=2000)
                    if element:
                        logger.info(f"✅ Success element found: {selector}")
                        return True
                except:
                    continue
            
            # Check URL changes that might indicate success
            current_url = page.url
            if any(word in current_url.lower() for word in ['success', 'confirmation', 'thank', 'submitted']):
                logger.info(f"✅ Success URL detected: {current_url}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error detecting success: {str(e)}")
            return False
    
    async def _human_like_delay(self, min_seconds: float = 1.0, max_seconds: float = 3.0):
        """Human-like delay with random variation"""
        delay = random.uniform(min_seconds, max_seconds)
        await asyncio.sleep(delay)
    
    async def _human_like_click(self, element):
        """Human-like clicking with random offset"""
        try:
            box = await element.bounding_box()
            if box:
                x = box['x'] + random.uniform(0.1, 0.9) * box['width']
                y = box['y'] + random.uniform(0.1, 0.9) * box['height']
                await element.click(position={'x': x - box['x'], 'y': y - box['y']})
            else:
                await element.click()
        except:
            await element.click()
    
    async def _find_element_smart(self, page: Page, selectors: List[str]):
        """Smart element finding with multiple strategies"""
        for selector in selectors:
            try:
                element = await page.wait_for_selector(selector, timeout=2000)
                if element:
                    return element
            except:
                continue
        return None
    
    async def _take_screenshot(self, page: Page, filename: str) -> str:
        """Take screenshot for debugging"""
        try:
            screenshot_path = self.screenshots_dir / f"{filename}_{int(time.time())}.png"
            await page.screenshot(path=screenshot_path)
            return str(screenshot_path)
        except Exception as e:
            logger.error(f"Error taking screenshot: {str(e)}")
            return ""
    
    # Placeholder methods for platform-specific implementations
    async def _apply_glassdoor_advanced(self, job_data: Dict[str, Any], user_profile: Dict[str, Any]) -> ApplicationResult:
        """Advanced Glassdoor application"""
        return await self._apply_generic_advanced(job_data, user_profile)
    
    async def _apply_google_advanced(self, job_data: Dict[str, Any], user_profile: Dict[str, Any]) -> ApplicationResult:
        """Advanced Google Jobs application"""
        return await self._apply_generic_advanced(job_data, user_profile)
    
    async def _apply_ziprecruiter_advanced(self, job_data: Dict[str, Any], user_profile: Dict[str, Any]) -> ApplicationResult:
        """Advanced ZipRecruiter application"""
        return await self._apply_generic_advanced(job_data, user_profile)
    
    async def _apply_bayt_advanced(self, job_data: Dict[str, Any], user_profile: Dict[str, Any]) -> ApplicationResult:
        """Advanced Bayt application"""
        return await self._apply_generic_advanced(job_data, user_profile)
    
    async def _apply_naukri_advanced(self, job_data: Dict[str, Any], user_profile: Dict[str, Any]) -> ApplicationResult:
        """Advanced Naukri application"""
        return await self._apply_generic_advanced(job_data, user_profile)
    
    async def _apply_lever_advanced(self, job_data: Dict[str, Any], user_profile: Dict[str, Any]) -> ApplicationResult:
        """Advanced Lever application"""
        return await self._apply_generic_advanced(job_data, user_profile)
    
    async def _apply_greenhouse_advanced(self, job_data: Dict[str, Any], user_profile: Dict[str, Any]) -> ApplicationResult:
        """Advanced Greenhouse application"""
        return await self._apply_generic_advanced(job_data, user_profile)
    
    async def _apply_workday_advanced(self, job_data: Dict[str, Any], user_profile: Dict[str, Any]) -> ApplicationResult:
        """Advanced Workday application"""
        return await self._apply_generic_advanced(job_data, user_profile)
    
    async def _apply_bamboohr_advanced(self, job_data: Dict[str, Any], user_profile: Dict[str, Any]) -> ApplicationResult:
        """Advanced BambooHR application"""
        return await self._apply_generic_advanced(job_data, user_profile)
    
    async def _apply_smartrecruiters_advanced(self, job_data: Dict[str, Any], user_profile: Dict[str, Any]) -> ApplicationResult:
        """Advanced SmartRecruiters application"""
        return await self._apply_generic_advanced(job_data, user_profile)
    
    async def _fill_indeed_form_advanced(self, page: Page, user_profile: Dict[str, Any]) -> bool:
        """Advanced Indeed form filling"""
        return await self._fill_generic_form_advanced(page, user_profile)
    
    async def _fill_linkedin_easy_apply_advanced(self, page: Page, user_profile: Dict[str, Any]) -> bool:
        """Advanced LinkedIn Easy Apply form filling"""
        return await self._fill_generic_form_advanced(page, user_profile)
    
    async def _handle_dropdown_fields(self, page: Page, user_profile: Dict[str, Any]):
        """Handle dropdown and select fields"""
        try:
            # Handle common dropdown fields
            dropdown_mappings = {
                'experience': user_profile.get('experience_years', '5'),
                'education': user_profile.get('education_level', 'Bachelor'),
                'location': user_profile.get('location', 'Remote'),
                'availability': user_profile.get('availability', 'Immediately')
            }
            
            for field_type, value in dropdown_mappings.items():
                if value:
                    selectors = [
                        f'select[name*="{field_type}"]',
                        f'select[id*="{field_type}"]'
                    ]
                    
                    for selector in selectors:
                        try:
                            select = await page.wait_for_selector(selector, timeout=2000)
                            if select:
                                await select.select_option(value=value)
                                break
                        except:
                            continue
        except Exception as e:
            logger.error(f"Error handling dropdown fields: {str(e)}")
    
    async def _handle_checkbox_fields(self, page: Page, user_profile: Dict[str, Any]):
        """Handle checkbox and radio button fields"""
        try:
            # Handle common checkboxes
            checkbox_selectors = [
                'input[type="checkbox"]',
                'input[type="radio"]'
            ]
            
            for selector in checkbox_selectors:
                try:
                    checkboxes = await page.query_selector_all(selector)
                    for checkbox in checkboxes:
                        # Check if it's a required field or terms acceptance
                        label = await checkbox.text_content()
                        if label and any(word in label.lower() for word in ['agree', 'terms', 'privacy', 'consent']):
                            await checkbox.check()
                except:
                    continue
        except Exception as e:
            logger.error(f"Error handling checkbox fields: {str(e)}")
    
    async def _try_drag_drop_upload(self, page: Page, file_path: str):
        """Try drag and drop file upload"""
        try:
            # Look for drag and drop zones
            drop_zones = [
                '.dropzone',
                '.drag-drop',
                '.file-upload',
                '[class*="drop"]',
                '[class*="upload"]'
            ]
            
            for zone_selector in drop_zones:
                try:
                    zone = await page.wait_for_selector(zone_selector, timeout=2000)
                    if zone:
                        # Simulate drag and drop
                        await zone.set_input_files(file_path)
                        logger.info("✅ File uploaded via drag and drop")
                        return True
                except:
                    continue
        except Exception as e:
            logger.error(f"Error with drag and drop upload: {str(e)}")
    
    async def apply_to_jobs_bulk(
        self, 
        jobs: List[Dict[str, Any]], 
        user_profile: Dict[str, Any],
        max_applications: int = 50
    ) -> List[ApplicationResult]:
        """
        Apply to multiple jobs in bulk with enhanced capabilities
        """
        results = []
        applied_count = 0
        
        # Shuffle jobs to avoid patterns
        shuffled_jobs = random.sample(jobs, min(len(jobs), max_applications))
        
        logger.info(f"🚀 Starting bulk application for {len(shuffled_jobs)} jobs")
        
        for i, job in enumerate(shuffled_jobs):
            if applied_count >= max_applications:
                break
                
            try:
                logger.info(f"📋 Processing job {i+1}/{len(shuffled_jobs)}: {job.get('title', 'Unknown')}")
                
                # Dynamic delay based on success rate
                base_delay = 15
                success_rate = applied_count / max(i, 1)
                if success_rate > 0.8:  # High success rate, be more careful
                    delay = base_delay * random.uniform(2, 4)
                else:
                    delay = base_delay * random.uniform(1, 2)
                
                await asyncio.sleep(delay)
                
                result = await self.apply_to_job(job, user_profile)
                results.append(result)
                
                if result.success:
                    applied_count += 1
                    logger.info(f"✅ Successfully applied ({applied_count}/{max_applications})")
                    
                    # Additional delay after successful application
                    await asyncio.sleep(random.uniform(30, 60))
                else:
                    logger.warning(f"❌ Application failed: {result.error_message}")
                    
            except Exception as e:
                logger.error(f"Error in bulk application: {str(e)}")
                results.append(ApplicationResult(
                    job_id=job.get('id', ''),
                    job_url=job.get('job_url', ''),
                    success=False,
                    status='failed',
                    error_message=str(e),
                    confidence_score=0.0
                ))
        
        success_count = len([r for r in results if r.success])
        logger.info(f"🎉 Bulk application completed: {success_count} successful applications out of {len(results)} attempts")
        
        return results

# Backward compatibility alias
JobApplicationBot = AdvancedJobApplicationBot

# Example usage
async def test_advanced_application_bot():
    """Test the advanced application bot"""
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
        'availability': 'Immediately',
        'experience_years': '5',
        'education_level': 'Bachelor',
        'location': 'Remote'
    }
    
    job_data = {
        'id': 'test-job-1',
        'job_url': 'https://example.com/job/123',
        'title': 'Software Engineer',
        'company': 'Tech Corp',
        'source': 'indeed'
    }
    
    async with AdvancedJobApplicationBot(headless=True, stealth_mode=True) as bot:
        result = await bot.apply_to_job(job_data, user_profile)
        print(f"Application result: {result}")
        print(f"Confidence score: {result.confidence_score}")

if __name__ == "__main__":
    asyncio.run(test_advanced_application_bot())