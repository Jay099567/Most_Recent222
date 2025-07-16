from celery import Celery
from celery.schedules import crontab
import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import json
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import uuid

# Import our custom modules
from job_scraper import JobScraper
from apply_bot import JobApplicationBot, ApplicationResult

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Celery app
app = Celery('autoapplyx')

# Celery configuration
app.conf.update(
    broker_url='redis://localhost:6379/0',
    result_backend='redis://localhost:6379/0',
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# Beat schedule for periodic tasks
app.conf.beat_schedule = {
    'daily-job-scraping': {
        'task': 'apply_tasks.daily_job_scraping_task',
        'schedule': crontab(hour=9, minute=0),  # 9 AM UTC daily
    },
    'daily-job-applications': {
        'task': 'apply_tasks.daily_job_applications_task',
        'schedule': crontab(hour=10, minute=0),  # 10 AM UTC daily
    },
    'cleanup-old-data': {
        'task': 'apply_tasks.cleanup_old_data_task',
        'schedule': crontab(hour=2, minute=0),  # 2 AM UTC daily
    },
}

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
db_name = os.environ.get('DB_NAME', 'test_database')

async def get_db():
    """Get database connection"""
    client = AsyncIOMotorClient(mongo_url)
    return client[db_name]

def run_async_task(coro):
    """Helper to run async tasks in Celery"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

@app.task(bind=True, max_retries=3)
def scrape_jobs_for_user_task(self, user_id: str, user_preferences: Dict[str, Any]):
    """
    Scrape jobs for a specific user
    
    Args:
        user_id: User ID
        user_preferences: User job preferences
        
    Returns:
        Dict with scraped jobs count and job IDs
    """
    try:
        logger.info(f"Starting job scraping for user {user_id}")
        
        async def _scrape_jobs():
            # Initialize scraper
            scraper = JobScraper(use_proxies=True, max_results_per_site=100)
            
            # Scrape jobs
            jobs = await scraper.scrape_jobs_for_user(user_preferences)
            
            if not jobs:
                logger.warning(f"No jobs found for user {user_id}")
                return {'jobs_count': 0, 'job_ids': []}
            
            # Store jobs in database
            db = await get_db()
            job_ids = []
            
            for job_data in jobs:
                # Create job object
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
                
                # Insert job into database
                await db.jobs.insert_one(job_obj)
                job_ids.append(job_obj['id'])
                
                # Update job matching
                await update_job_matches(user_id, job_obj)
            
            logger.info(f"Scraped {len(jobs)} jobs for user {user_id}")
            return {'jobs_count': len(jobs), 'job_ids': job_ids}
        
        return run_async_task(_scrape_jobs())
        
    except Exception as e:
        logger.error(f"Error scraping jobs for user {user_id}: {str(e)}")
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))

@app.task(bind=True, max_retries=3)
def apply_to_jobs_for_user_task(self, user_id: str, max_applications: int = 50):
    """
    Apply to jobs for a specific user
    
    Args:
        user_id: User ID
        max_applications: Maximum number of applications to submit
        
    Returns:
        Dict with application results
    """
    try:
        logger.info(f"Starting job applications for user {user_id}")
        
        async def _apply_to_jobs():
            db = await get_db()
            
            # Get user profile
            user = await db.users.find_one({'id': user_id})
            if not user:
                logger.error(f"User {user_id} not found")
                return {'success': False, 'error': 'User not found'}
            
            # Get pending jobs for this user
            pending_jobs = await db.jobs.find({
                'user_id': user_id,
                'applied': False,
                'application_status': 'pending'
            }).limit(max_applications).to_list(max_applications)
            
            if not pending_jobs:
                logger.info(f"No pending jobs for user {user_id}")
                return {'applications_count': 0, 'successful_applications': 0}
            
            # Prepare user profile for application bot
            user_profile = {
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
            
            # Initialize application bot
            async with JobApplicationBot(headless=True) as bot:
                results = await bot.apply_to_jobs_bulk(pending_jobs, user_profile, max_applications)
            
            # Update database with application results
            successful_applications = 0
            for result in results:
                try:
                    application_record = {
                        'id': str(uuid.uuid4()),
                        'user_id': user_id,
                        'job_id': result.job_id,
                        'status': result.status,
                        'applied_at': result.applied_at or datetime.utcnow(),
                        'error_message': result.error_message,
                        'application_id': result.application_id,
                        'retry_count': result.retry_count
                    }
                    
                    # Insert application record
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
                    
                    if result.success:
                        successful_applications += 1
                        
                except Exception as e:
                    logger.error(f"Error updating application record: {str(e)}")
            
            logger.info(f"Applied to {successful_applications} jobs for user {user_id}")
            return {
                'applications_count': len(results),
                'successful_applications': successful_applications,
                'failed_applications': len(results) - successful_applications
            }
        
        return run_async_task(_apply_to_jobs())
        
    except Exception as e:
        logger.error(f"Error applying to jobs for user {user_id}: {str(e)}")
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))

@app.task
def daily_job_scraping_task():
    """
    Daily task to scrape jobs for all active users
    """
    try:
        logger.info("Starting daily job scraping task")
        
        async def _daily_scraping():
            db = await get_db()
            
            # Get all active users
            users = await db.users.find({'active': {'$ne': False}}).to_list(1000)
            
            scraping_results = []
            for user in users:
                user_id = user['id']
                
                # Default preferences if not set
                user_preferences = user.get('job_preferences', {})
                if not user_preferences:
                    user_preferences = {
                        'keywords': user.get('skills', ['software engineer']),
                        'location': 'Remote',
                        'job_type': 'fulltime',
                        'is_remote': True,
                        'hours_old': 24
                    }
                
                # Queue scraping task for this user
                try:
                    result = scrape_jobs_for_user_task.delay(user_id, user_preferences)
                    scraping_results.append({
                        'user_id': user_id,
                        'task_id': result.id,
                        'status': 'queued'
                    })
                except Exception as e:
                    logger.error(f"Error queuing scraping task for user {user_id}: {str(e)}")
                    scraping_results.append({
                        'user_id': user_id,
                        'task_id': None,
                        'status': 'failed',
                        'error': str(e)
                    })
            
            # Log scraping task
            scraping_task = {
                'id': str(uuid.uuid4()),
                'type': 'daily_scraping',
                'status': 'completed',
                'users_processed': len(users),
                'tasks_queued': len([r for r in scraping_results if r['status'] == 'queued']),
                'created_at': datetime.utcnow(),
                'results': scraping_results
            }
            
            await db.scraping_tasks.insert_one(scraping_task)
            
            logger.info(f"Daily scraping task completed. Processed {len(users)} users")
            return scraping_task
        
        return run_async_task(_daily_scraping())
        
    except Exception as e:
        logger.error(f"Error in daily job scraping task: {str(e)}")
        return {'error': str(e)}

@app.task
def daily_job_applications_task():
    """
    Daily task to apply to jobs for all active users
    """
    try:
        logger.info("Starting daily job applications task")
        
        async def _daily_applications():
            db = await get_db()
            
            # Get all active users
            users = await db.users.find({'active': {'$ne': False}}).to_list(1000)
            
            application_results = []
            for user in users:
                user_id = user['id']
                max_applications = user.get('max_daily_applications', 20)
                
                # Queue application task for this user
                try:
                    result = apply_to_jobs_for_user_task.delay(user_id, max_applications)
                    application_results.append({
                        'user_id': user_id,
                        'task_id': result.id,
                        'status': 'queued',
                        'max_applications': max_applications
                    })
                except Exception as e:
                    logger.error(f"Error queuing application task for user {user_id}: {str(e)}")
                    application_results.append({
                        'user_id': user_id,
                        'task_id': None,
                        'status': 'failed',
                        'error': str(e)
                    })
            
            # Log application task
            application_task = {
                'id': str(uuid.uuid4()),
                'type': 'daily_applications',
                'status': 'completed',
                'users_processed': len(users),
                'tasks_queued': len([r for r in application_results if r['status'] == 'queued']),
                'created_at': datetime.utcnow(),
                'results': application_results
            }
            
            await db.scraping_tasks.insert_one(application_task)
            
            logger.info(f"Daily applications task completed. Processed {len(users)} users")
            return application_task
        
        return run_async_task(_daily_applications())
        
    except Exception as e:
        logger.error(f"Error in daily job applications task: {str(e)}")
        return {'error': str(e)}

@app.task
def cleanup_old_data_task():
    """
    Cleanup old data to keep database size manageable
    """
    try:
        logger.info("Starting cleanup task")
        
        async def _cleanup():
            db = await get_db()
            
            # Delete jobs older than 30 days
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            old_jobs_result = await db.jobs.delete_many({
                'scraped_at': {'$lt': thirty_days_ago}
            })
            
            # Delete old scraping tasks (keep last 100)
            scraping_tasks = await db.scraping_tasks.find().sort('created_at', -1).skip(100).to_list(1000)
            if scraping_tasks:
                old_task_ids = [task['id'] for task in scraping_tasks]
                await db.scraping_tasks.delete_many({'id': {'$in': old_task_ids}})
            
            # Delete old application records (keep last 1000 per user)
            users = await db.users.find().to_list(1000)
            for user in users:
                applications = await db.applications.find({'user_id': user['id']}).sort('applied_at', -1).skip(1000).to_list(1000)
                if applications:
                    old_app_ids = [app['id'] for app in applications]
                    await db.applications.delete_many({'id': {'$in': old_app_ids}})
            
            cleanup_result = {
                'old_jobs_deleted': old_jobs_result.deleted_count,
                'old_scraping_tasks_deleted': len(scraping_tasks),
                'cleanup_date': datetime.utcnow()
            }
            
            logger.info(f"Cleanup completed: {cleanup_result}")
            return cleanup_result
        
        return run_async_task(_cleanup())
        
    except Exception as e:
        logger.error(f"Error in cleanup task: {str(e)}")
        return {'error': str(e)}

async def update_job_matches(user_id: str, job_data: Dict[str, Any]):
    """
    Update job matches in vector database
    
    Args:
        user_id: User ID
        job_data: Job data to match against
    """
    try:
        from sentence_transformers import SentenceTransformer
        import chromadb
        import numpy as np
        from sklearn.metrics.pairwise import cosine_similarity
        
        # Initialize components
        embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        chroma_client = chromadb.PersistentClient(path="./chroma_db")
        resume_collection = chroma_client.get_or_create_collection("resumes")
        job_collection = chroma_client.get_or_create_collection("jobs")
        
        # Generate job embedding
        job_text = f"{job_data['title']} {job_data['description']} {' '.join(job_data.get('requirements', []))}"
        job_embedding = embedding_model.encode(job_text)
        
        # Store job embedding
        job_collection.upsert(
            ids=[job_data['id']],
            embeddings=[job_embedding.tolist()],
            metadatas=[{
                'title': job_data['title'],
                'company': job_data['company'],
                'location': job_data['location'],
                'requirements': json.dumps(job_data.get('requirements', [])),
                'source': job_data['source'],
                'user_id': user_id
            }]
        )
        
        # Calculate similarity with user's resume
        user_results = resume_collection.get(ids=[user_id], include=['embeddings'])
        if user_results['ids']:
            user_embedding = np.array(user_results['embeddings'][0]).reshape(1, -1)
            job_embedding_array = np.array(job_embedding).reshape(1, -1)
            
            similarity_score = cosine_similarity(user_embedding, job_embedding_array)[0][0]
            
            # Store job match if similarity is high enough
            if similarity_score > 0.3:  # 30% similarity threshold
                db = await get_db()
                match_record = {
                    'id': str(uuid.uuid4()),
                    'user_id': user_id,
                    'job_id': job_data['id'],
                    'similarity_score': float(similarity_score),
                    'matching_skills': [],  # Will be populated later
                    'match_reasons': [f"Similarity: {similarity_score:.2%}"],
                    'created_at': datetime.utcnow()
                }
                
                await db.job_matches.insert_one(match_record)
        
    except Exception as e:
        logger.error(f"Error updating job matches: {str(e)}")

# Manual task triggers for testing
@app.task
def trigger_scraping_for_user(user_id: str):
    """Manually trigger scraping for a user"""
    return scrape_jobs_for_user_task.delay(user_id, {})

@app.task
def trigger_applications_for_user(user_id: str):
    """Manually trigger applications for a user"""
    return apply_to_jobs_for_user_task.delay(user_id, 10)

if __name__ == '__main__':
    app.start()