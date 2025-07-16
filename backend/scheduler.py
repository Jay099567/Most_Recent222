import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
import json
import uuid
from contextlib import asynccontextmanager

# Import our modules
from job_scraper import JobScraper
from apply_bot import JobApplicationBot
from apply_tasks import (
    scrape_jobs_for_user_task,
    apply_to_jobs_for_user_task,
    daily_job_scraping_task,
    daily_job_applications_task,
    cleanup_old_data_task
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AutoApplyScheduler:
    """
    Main scheduler for AutoApplyX autonomous job application system
    Coordinates daily scraping, matching, and applying workflow
    """
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        self.db_name = os.environ.get('DB_NAME', 'test_database')
        self.running = False
        
        # Performance tracking
        self.stats = {
            'total_jobs_scraped': 0,
            'total_applications_sent': 0,
            'successful_applications': 0,
            'failed_applications': 0,
            'users_processed': 0,
            'last_run': None,
            'uptime_start': datetime.utcnow()
        }
        
    async def start(self):
        """Start the scheduler"""
        try:
            logger.info("Starting AutoApplyX Scheduler...")
            
            # Configure scheduler jobs
            await self._configure_jobs()
            
            # Start the scheduler
            self.scheduler.start()
            self.running = True
            
            logger.info("AutoApplyX Scheduler started successfully")
            
            # Log initial status
            await self._log_scheduler_status('started')
            
        except Exception as e:
            logger.error(f"Error starting scheduler: {str(e)}")
            raise
    
    async def stop(self):
        """Stop the scheduler"""
        try:
            logger.info("Stopping AutoApplyX Scheduler...")
            
            if self.scheduler.running:
                self.scheduler.shutdown()
            
            self.running = False
            
            # Log final status
            await self._log_scheduler_status('stopped')
            
            logger.info("AutoApplyX Scheduler stopped successfully")
            
        except Exception as e:
            logger.error(f"Error stopping scheduler: {str(e)}")
    
    async def _configure_jobs(self):
        """Configure all scheduled jobs"""
        try:
            # Daily job scraping at 9 AM UTC
            self.scheduler.add_job(
                func=self._daily_scraping_workflow,
                trigger=CronTrigger(hour=9, minute=0),
                id='daily_scraping',
                name='Daily Job Scraping',
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=3600  # 1 hour
            )
            
            # Daily job applications at 10 AM UTC (after scraping)
            self.scheduler.add_job(
                func=self._daily_applications_workflow,
                trigger=CronTrigger(hour=10, minute=0),
                id='daily_applications',
                name='Daily Job Applications',
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=3600  # 1 hour
            )
            
            # Continuous application workflow (every 2 hours during business hours)
            self.scheduler.add_job(
                func=self._continuous_applications_workflow,
                trigger=CronTrigger(hour='8-18', minute=0),
                id='continuous_applications',
                name='Continuous Applications',
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=1800  # 30 minutes
            )
            
            # Data cleanup at 2 AM UTC
            self.scheduler.add_job(
                func=self._cleanup_workflow,
                trigger=CronTrigger(hour=2, minute=0),
                id='data_cleanup',
                name='Data Cleanup',
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=3600  # 1 hour
            )
            
            # Stats update every hour
            self.scheduler.add_job(
                func=self._update_stats,
                trigger=IntervalTrigger(hours=1),
                id='stats_update',
                name='Stats Update',
                replace_existing=True,
                max_instances=1
            )
            
            # Health check every 30 minutes
            self.scheduler.add_job(
                func=self._health_check,
                trigger=IntervalTrigger(minutes=30),
                id='health_check',
                name='Health Check',
                replace_existing=True,
                max_instances=1
            )
            
            logger.info("Scheduler jobs configured successfully")
            
        except Exception as e:
            logger.error(f"Error configuring scheduler jobs: {str(e)}")
            raise
    
    async def _daily_scraping_workflow(self):
        """Daily workflow for scraping jobs from all job boards"""
        try:
            logger.info("Starting daily scraping workflow")
            
            db = await self._get_db()
            
            # Get all active users
            users = await db.users.find({'active': {'$ne': False}}).to_list(1000)
            logger.info(f"Processing {len(users)} active users for scraping")
            
            # Execute scraping for each user
            scraping_results = []
            scraper = JobScraper(use_proxies=True, max_results_per_site=100)
            
            for user in users:
                try:
                    user_id = user['id']
                    
                    # Get user job preferences
                    user_preferences = user.get('job_preferences', {})
                    if not user_preferences:
                        # Default preferences based on user's skills
                        user_preferences = {
                            'keywords': user.get('skills', ['software engineer']),
                            'location': user.get('preferred_location', 'Remote'),
                            'job_type': user.get('preferred_job_type', 'fulltime'),
                            'is_remote': user.get('prefer_remote', True),
                            'hours_old': 24,  # Last 24 hours
                            'user_id': user_id
                        }
                    
                    # Scrape jobs for this user
                    jobs = await scraper.scrape_jobs_for_user(user_preferences)
                    
                    # Store scraped jobs
                    stored_jobs = await self._store_scraped_jobs(user_id, jobs)
                    
                    scraping_results.append({
                        'user_id': user_id,
                        'jobs_scraped': len(jobs),
                        'jobs_stored': len(stored_jobs),
                        'status': 'success'
                    })
                    
                    self.stats['total_jobs_scraped'] += len(jobs)
                    
                    # Small delay between users
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    logger.error(f"Error scraping jobs for user {user['id']}: {str(e)}")
                    scraping_results.append({
                        'user_id': user['id'],
                        'jobs_scraped': 0,
                        'jobs_stored': 0,
                        'status': 'failed',
                        'error': str(e)
                    })
            
            # Log scraping workflow results
            workflow_result = {
                'id': str(uuid.uuid4()),
                'type': 'daily_scraping_workflow',
                'status': 'completed',
                'users_processed': len(users),
                'total_jobs_scraped': sum(r['jobs_scraped'] for r in scraping_results),
                'successful_users': len([r for r in scraping_results if r['status'] == 'success']),
                'failed_users': len([r for r in scraping_results if r['status'] == 'failed']),
                'created_at': datetime.utcnow(),
                'results': scraping_results
            }
            
            await db.workflow_logs.insert_one(workflow_result)
            
            self.stats['users_processed'] = len(users)
            self.stats['last_run'] = datetime.utcnow()
            
            logger.info(f"Daily scraping workflow completed. Processed {len(users)} users, scraped {workflow_result['total_jobs_scraped']} jobs")
            
        except Exception as e:
            logger.error(f"Error in daily scraping workflow: {str(e)}")
            await self._log_error('daily_scraping_workflow', str(e))
    
    async def _daily_applications_workflow(self):
        """Daily workflow for applying to jobs"""
        try:
            logger.info("Starting daily applications workflow")
            
            db = await self._get_db()
            
            # Get all active users
            users = await db.users.find({'active': {'$ne': False}}).to_list(1000)
            logger.info(f"Processing {len(users)} active users for applications")
            
            # Execute applications for each user
            application_results = []
            
            for user in users:
                try:
                    user_id = user['id']
                    max_applications = user.get('max_daily_applications', 20)
                    
                    # Get user's top job matches
                    job_matches = await db.job_matches.find({
                        'user_id': user_id
                    }).sort('similarity_score', -1).limit(max_applications).to_list(max_applications)
                    
                    if not job_matches:
                        logger.info(f"No job matches found for user {user_id}")
                        continue
                    
                    # Get full job details
                    job_ids = [match['job_id'] for match in job_matches]
                    jobs = await db.jobs.find({
                        'id': {'$in': job_ids},
                        'applied': {'$ne': True}
                    }).to_list(max_applications)
                    
                    if not jobs:
                        logger.info(f"No unapplied jobs found for user {user_id}")
                        continue
                    
                    # Prepare user profile
                    user_profile = await self._prepare_user_profile(user)
                    
                    # Apply to jobs
                    async with JobApplicationBot(headless=True) as bot:
                        results = await bot.apply_to_jobs_bulk(jobs, user_profile, max_applications)
                    
                    # Process results
                    successful_applications = 0
                    failed_applications = 0
                    
                    for result in results:
                        # Store application record
                        await self._store_application_result(user_id, result)
                        
                        if result.success:
                            successful_applications += 1
                            self.stats['successful_applications'] += 1
                        else:
                            failed_applications += 1
                            self.stats['failed_applications'] += 1
                        
                        self.stats['total_applications_sent'] += 1
                    
                    application_results.append({
                        'user_id': user_id,
                        'applications_attempted': len(results),
                        'successful_applications': successful_applications,
                        'failed_applications': failed_applications,
                        'status': 'success'
                    })
                    
                    # Delay between users to avoid rate limiting
                    await asyncio.sleep(30)
                    
                except Exception as e:
                    logger.error(f"Error applying to jobs for user {user['id']}: {str(e)}")
                    application_results.append({
                        'user_id': user['id'],
                        'applications_attempted': 0,
                        'successful_applications': 0,
                        'failed_applications': 0,
                        'status': 'failed',
                        'error': str(e)
                    })
            
            # Log application workflow results
            workflow_result = {
                'id': str(uuid.uuid4()),
                'type': 'daily_applications_workflow',
                'status': 'completed',
                'users_processed': len(users),
                'total_applications_attempted': sum(r['applications_attempted'] for r in application_results),
                'total_successful_applications': sum(r['successful_applications'] for r in application_results),
                'total_failed_applications': sum(r['failed_applications'] for r in application_results),
                'created_at': datetime.utcnow(),
                'results': application_results
            }
            
            await db.workflow_logs.insert_one(workflow_result)
            
            logger.info(f"Daily applications workflow completed. Processed {len(users)} users, attempted {workflow_result['total_applications_attempted']} applications")
            
        except Exception as e:
            logger.error(f"Error in daily applications workflow: {str(e)}")
            await self._log_error('daily_applications_workflow', str(e))
    
    async def _continuous_applications_workflow(self):
        """Continuous workflow for ongoing applications during business hours"""
        try:
            logger.info("Starting continuous applications workflow")
            
            db = await self._get_db()
            
            # Get users with recent job matches but no recent applications
            recent_cutoff = datetime.utcnow() - timedelta(hours=2)
            
            users_with_matches = await db.job_matches.aggregate([
                {
                    '$match': {
                        'created_at': {'$gte': recent_cutoff},
                        'similarity_score': {'$gte': 0.5}  # High similarity matches
                    }
                },
                {
                    '$group': {
                        '_id': '$user_id',
                        'match_count': {'$sum': 1},
                        'avg_similarity': {'$avg': '$similarity_score'}
                    }
                },
                {
                    '$match': {
                        'match_count': {'$gte': 3}  # At least 3 good matches
                    }
                }
            ]).to_list(100)
            
            if not users_with_matches:
                logger.info("No users with recent high-quality matches found")
                return
            
            # Process each user
            for user_match in users_with_matches:
                try:
                    user_id = user_match['_id']
                    
                    # Get user details
                    user = await db.users.find_one({'id': user_id})
                    if not user or user.get('active') == False:
                        continue
                    
                    # Check if user has reached daily application limit
                    daily_apps = await db.applications.count_documents({
                        'user_id': user_id,
                        'applied_at': {'$gte': datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)}
                    })
                    
                    max_daily = user.get('max_daily_applications', 20)
                    if daily_apps >= max_daily:
                        logger.info(f"User {user_id} has reached daily application limit ({daily_apps}/{max_daily})")
                        continue
                    
                    # Apply to a few high-quality matches
                    remaining_apps = min(5, max_daily - daily_apps)
                    
                    # Get top matches for this user
                    job_matches = await db.job_matches.find({
                        'user_id': user_id,
                        'similarity_score': {'$gte': 0.5}
                    }).sort('similarity_score', -1).limit(remaining_apps).to_list(remaining_apps)
                    
                    if not job_matches:
                        continue
                    
                    # Get job details
                    job_ids = [match['job_id'] for match in job_matches]
                    jobs = await db.jobs.find({
                        'id': {'$in': job_ids},
                        'applied': {'$ne': True}
                    }).to_list(remaining_apps)
                    
                    if not jobs:
                        continue
                    
                    # Prepare user profile and apply
                    user_profile = await self._prepare_user_profile(user)
                    
                    async with JobApplicationBot(headless=True) as bot:
                        results = await bot.apply_to_jobs_bulk(jobs, user_profile, remaining_apps)
                    
                    # Process results
                    for result in results:
                        await self._store_application_result(user_id, result)
                    
                    successful_apps = len([r for r in results if r.success])
                    logger.info(f"Continuous workflow: Applied to {successful_apps} jobs for user {user_id}")
                    
                    # Delay between users
                    await asyncio.sleep(60)
                    
                except Exception as e:
                    logger.error(f"Error in continuous workflow for user {user_match['_id']}: {str(e)}")
            
            logger.info("Continuous applications workflow completed")
            
        except Exception as e:
            logger.error(f"Error in continuous applications workflow: {str(e)}")
    
    async def _cleanup_workflow(self):
        """Cleanup old data to maintain performance"""
        try:
            logger.info("Starting cleanup workflow")
            
            db = await self._get_db()
            
            # Delete old jobs (30 days)
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            old_jobs = await db.jobs.delete_many({
                'scraped_at': {'$lt': thirty_days_ago}
            })
            
            # Delete old workflow logs (keep last 1000)
            old_logs = await db.workflow_logs.find().sort('created_at', -1).skip(1000).to_list(1000)
            if old_logs:
                log_ids = [log['id'] for log in old_logs]
                await db.workflow_logs.delete_many({'id': {'$in': log_ids}})
            
            # Delete old job matches (60 days)
            sixty_days_ago = datetime.utcnow() - timedelta(days=60)
            old_matches = await db.job_matches.delete_many({
                'created_at': {'$lt': sixty_days_ago}
            })
            
            cleanup_result = {
                'old_jobs_deleted': old_jobs.deleted_count,
                'old_logs_deleted': len(old_logs),
                'old_matches_deleted': old_matches.deleted_count,
                'cleanup_date': datetime.utcnow()
            }
            
            logger.info(f"Cleanup completed: {cleanup_result}")
            
        except Exception as e:
            logger.error(f"Error in cleanup workflow: {str(e)}")
    
    async def _update_stats(self):
        """Update system statistics"""
        try:
            db = await self._get_db()
            
            # Calculate today's stats
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            
            today_applications = await db.applications.count_documents({
                'applied_at': {'$gte': today}
            })
            
            today_jobs = await db.jobs.count_documents({
                'scraped_at': {'$gte': today}
            })
            
            active_users = await db.users.count_documents({
                'active': {'$ne': False}
            })
            
            # Update stats
            stats_record = {
                'id': str(uuid.uuid4()),
                'date': today,
                'total_jobs_scraped_today': today_jobs,
                'total_applications_today': today_applications,
                'active_users': active_users,
                'system_uptime': datetime.utcnow() - self.stats['uptime_start'],
                'created_at': datetime.utcnow()
            }
            
            await db.system_stats.insert_one(stats_record)
            
            logger.info(f"Stats updated: {stats_record}")
            
        except Exception as e:
            logger.error(f"Error updating stats: {str(e)}")
    
    async def _health_check(self):
        """Perform system health check"""
        try:
            db = await self._get_db()
            
            # Check database connectivity
            await db.command('ping')
            
            # Check recent activity
            recent_activity = await db.applications.count_documents({
                'applied_at': {'$gte': datetime.utcnow() - timedelta(hours=24)}
            })
            
            health_status = {
                'timestamp': datetime.utcnow(),
                'database_connected': True,
                'scheduler_running': self.scheduler.running,
                'recent_applications': recent_activity,
                'status': 'healthy'
            }
            
            logger.info(f"Health check passed: {health_status}")
            
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            await self._log_error('health_check', str(e))
    
    async def _get_db(self):
        """Get database connection"""
        client = AsyncIOMotorClient(self.mongo_url)
        return client[self.db_name]
    
    async def _store_scraped_jobs(self, user_id: str, jobs: List[Dict[str, Any]]) -> List[str]:
        """Store scraped jobs in database"""
        try:
            db = await self._get_db()
            stored_jobs = []
            
            for job_data in jobs:
                job_obj = {
                    'id': str(uuid.uuid4()),
                    'user_id': user_id,
                    'title': job_data.get('title', ''),
                    'company': job_data.get('company', ''),
                    'location': job_data.get('location', ''),
                    'description': job_data.get('description', ''),
                    'requirements': job_data.get('requirements', []),
                    'salary_range': f"{job_data.get('salary_min', 0)}-{job_data.get('salary_max', 0)}",
                    'job_type': job_data.get('job_type', 'fulltime'),
                    'source': job_data.get('source', ''),
                    'url': job_data.get('job_url', ''),
                    'is_remote': job_data.get('is_remote', False),
                    'posted_date': job_data.get('date_posted', datetime.utcnow()),
                    'scraped_at': datetime.utcnow(),
                    'applied': False,
                    'application_status': 'pending'
                }
                
                # Check if job already exists
                existing_job = await db.jobs.find_one({
                    'url': job_obj['url'],
                    'user_id': user_id
                })
                
                if not existing_job:
                    await db.jobs.insert_one(job_obj)
                    stored_jobs.append(job_obj['id'])
                    
                    # Update job matches
                    await self._update_job_matches(user_id, job_obj)
            
            return stored_jobs
            
        except Exception as e:
            logger.error(f"Error storing scraped jobs: {str(e)}")
            return []
    
    async def _update_job_matches(self, user_id: str, job_data: Dict[str, Any]):
        """Update job matches using vector similarity"""
        try:
            # This would integrate with the existing matching logic
            # For now, we'll create a simple match record
            db = await self._get_db()
            
            match_record = {
                'id': str(uuid.uuid4()),
                'user_id': user_id,
                'job_id': job_data['id'],
                'similarity_score': 0.7,  # Placeholder
                'matching_skills': job_data.get('requirements', []),
                'match_reasons': ['New job match'],
                'created_at': datetime.utcnow()
            }
            
            await db.job_matches.insert_one(match_record)
            
        except Exception as e:
            logger.error(f"Error updating job matches: {str(e)}")
    
    async def _prepare_user_profile(self, user: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare user profile for application bot"""
        return {
            'name': user.get('name', ''),
            'email': user.get('email', ''),
            'phone': user.get('phone', ''),
            'first_name': user.get('name', '').split()[0] if user.get('name') else '',
            'last_name': user.get('name', '').split()[-1] if user.get('name') else '',
            'linkedin_url': user.get('linkedin_url', ''),
            'portfolio_url': user.get('portfolio_url', ''),
            'cover_letter': user.get('cover_letter', ''),
            'salary_expectation': user.get('salary_expectation', ''),
            'availability': user.get('availability', 'Immediately'),
            'resume_path': user.get('resume_path', '')
        }
    
    async def _store_application_result(self, user_id: str, result):
        """Store application result in database"""
        try:
            db = await self._get_db()
            
            # Store application record
            application_record = {
                'id': str(uuid.uuid4()),
                'user_id': user_id,
                'job_id': result.job_id,
                'status': result.status,
                'applied_at': result.applied_at or datetime.utcnow(),
                'error_message': result.error_message,
                'application_id': result.application_id,
                'retry_count': result.retry_count,
                'success': result.success
            }
            
            await db.applications.insert_one(application_record)
            
            # Update job status
            await db.jobs.update_one(
                {'id': result.job_id},
                {
                    '$set': {
                        'applied': result.success,
                        'application_status': result.status,
                        'application_date': result.applied_at or datetime.utcnow(),
                        'error_message': result.error_message
                    }
                }
            )
            
        except Exception as e:
            logger.error(f"Error storing application result: {str(e)}")
    
    async def _log_scheduler_status(self, status: str):
        """Log scheduler status"""
        try:
            db = await self._get_db()
            
            status_record = {
                'id': str(uuid.uuid4()),
                'status': status,
                'timestamp': datetime.utcnow(),
                'stats': self.stats.copy()
            }
            
            await db.scheduler_logs.insert_one(status_record)
            
        except Exception as e:
            logger.error(f"Error logging scheduler status: {str(e)}")
    
    async def _log_error(self, component: str, error: str):
        """Log error to database"""
        try:
            db = await self._get_db()
            
            error_record = {
                'id': str(uuid.uuid4()),
                'component': component,
                'error_message': error,
                'timestamp': datetime.utcnow(),
                'severity': 'error'
            }
            
            await db.error_logs.insert_one(error_record)
            
        except Exception as e:
            logger.error(f"Error logging error: {str(e)}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current system statistics"""
        return {
            **self.stats,
            'running': self.running,
            'uptime': datetime.utcnow() - self.stats['uptime_start']
        }
    
    @asynccontextmanager
    async def run_context(self):
        """Context manager for running the scheduler"""
        await self.start()
        try:
            yield self
        finally:
            await self.stop()

# Main function to run the scheduler
async def main():
    """Main function to run the AutoApplyX scheduler"""
    scheduler = AutoApplyScheduler()
    
    try:
        async with scheduler.run_context():
            logger.info("AutoApplyX Scheduler is running. Press Ctrl+C to stop.")
            
            # Keep the scheduler running
            while True:
                await asyncio.sleep(60)
                
                # Print stats every hour
                if datetime.utcnow().minute == 0:
                    stats = scheduler.get_stats()
                    logger.info(f"Current stats: {stats}")
                
    except KeyboardInterrupt:
        logger.info("Shutting down scheduler...")
    except Exception as e:
        logger.error(f"Scheduler error: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main())