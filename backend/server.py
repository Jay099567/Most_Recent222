from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timedelta
import json
from sentence_transformers import SentenceTransformer
import chromadb
import asyncio
import aiofiles
import PyPDF2
import io
import re
from collections import defaultdict
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import hashlib

# Import AI modules
try:
    from ai_application_bot import AIJobApplicationBot
    from advanced_job_scraper import AdvancedJobScraper
    import requests
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.warning(f"AI modules not available: {e}")
    AIJobApplicationBot = None
    AdvancedJobScraper = None

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Initialize sentence transformer for embeddings
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

# Initialize Chroma vector database
chroma_client = chromadb.PersistentClient(path="./chroma_db")
resume_collection = chroma_client.get_or_create_collection("resumes")
job_collection = chroma_client.get_or_create_collection("jobs")

# Create the main app
app = FastAPI(title="AutoApplyX", description="Autonomous Job Application System")
api_router = APIRouter(prefix="/api")

# Pydantic Models
class UserProfile(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    email: str
    resume_text: str = ""
    skills: List[str] = []
    experience_years: int = 0
    job_preferences: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
class UserProfileCreate(BaseModel):
    name: str
    email: str

class JobListing(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    company: str
    location: str
    description: str
    requirements: List[str] = []
    salary_range: Optional[str] = None
    job_type: str = "full-time"
    source: str  # indeed, linkedin, google
    url: str
    posted_date: datetime = Field(default_factory=datetime.utcnow)
    scraped_at: datetime = Field(default_factory=datetime.utcnow)

class JobMatch(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    job_id: str
    similarity_score: float
    matching_skills: List[str] = []
    match_reasons: List[str] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)

class ApplicationRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    job_id: str
    status: str = "pending"  # pending, applied, failed, rejected
    applied_at: datetime = Field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None
    retry_count: int = 0

class ScrapingTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    keywords: List[str]
    location: str
    status: str = "pending"  # pending, running, completed, failed
    jobs_found: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

# Resume parsing utilities
def extract_text_from_pdf(pdf_content: bytes) -> str:
    """Extract text from PDF resume"""
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading PDF: {str(e)}")

def extract_skills_from_resume(resume_text: str) -> List[str]:
    """Extract skills from resume text using pattern matching"""
    # Common tech skills patterns
    tech_skills = [
        'python', 'java', 'javascript', 'react', 'nodejs', 'angular', 'vue',
        'html', 'css', 'sql', 'mongodb', 'postgresql', 'mysql', 'docker',
        'kubernetes', 'aws', 'azure', 'gcp', 'git', 'linux', 'bash',
        'tensorflow', 'pytorch', 'pandas', 'numpy', 'fastapi', 'django',
        'flask', 'spring', 'express', 'bootstrap', 'tailwind', 'typescript',
        'c++', 'c#', 'go', 'rust', 'php', 'ruby', 'scala', 'kotlin',
        'swift', 'flutter', 'react native', 'unity', 'firebase'
    ]
    
    resume_lower = resume_text.lower()
    found_skills = []
    
    for skill in tech_skills:
        if skill in resume_lower:
            found_skills.append(skill)
    
    # Extract years of experience
    experience_pattern = r'(\d+)\+?\s*years?\s*(?:of\s*)?(?:experience|exp)'
    experience_matches = re.findall(experience_pattern, resume_lower)
    
    return found_skills

def calculate_experience_years(resume_text: str) -> int:
    """Calculate years of experience from resume"""
    experience_pattern = r'(\d+)\+?\s*years?\s*(?:of\s*)?(?:experience|exp)'
    matches = re.findall(experience_pattern, resume_text.lower())
    return max([int(match) for match in matches]) if matches else 0

# API Routes
@api_router.get("/")
async def root():
    return {"message": "AutoApplyX - Autonomous Job Application System"}

@api_router.post("/users", response_model=UserProfile)
async def create_user(user_data: UserProfileCreate):
    """Create a new user profile"""
    user_dict = user_data.dict()
    user_obj = UserProfile(**user_dict)
    await db.users.insert_one(user_obj.dict())
    return user_obj

@api_router.get("/users", response_model=List[UserProfile])
async def get_users():
    """Get all users"""
    users = await db.users.find().to_list(1000)
    return [UserProfile(**user) for user in users]

@api_router.get("/users/{user_id}", response_model=UserProfile)
async def get_user(user_id: str):
    """Get a specific user"""
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserProfile(**user)

@api_router.post("/users/{user_id}/upload-resume")
async def upload_resume(user_id: str, file: UploadFile = File(...)):
    """Upload and process resume"""
    try:
        # Read file content
        content = await file.read()
        
        # Extract text based on file type
        if file.content_type == "application/pdf":
            resume_text = extract_text_from_pdf(content)
        elif file.content_type == "text/plain":
            resume_text = content.decode('utf-8')
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type. Please upload PDF or TXT file.")
        
        # Extract skills and experience
        skills = extract_skills_from_resume(resume_text)
        experience_years = calculate_experience_years(resume_text)
        
        # Generate embeddings
        embedding = embedding_model.encode(resume_text)
        
        # Store in vector database
        resume_collection.upsert(
            ids=[user_id],
            embeddings=[embedding.tolist()],
            metadatas=[{"user_id": user_id, "skills": json.dumps(skills), "experience_years": experience_years}]
        )
        
        # Update user profile
        await db.users.update_one(
            {"id": user_id},
            {"$set": {
                "resume_text": resume_text,
                "skills": skills,
                "experience_years": experience_years
            }}
        )
        
        return {
            "message": "Resume uploaded successfully",
            "skills_extracted": skills,
            "experience_years": experience_years
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing resume: {str(e)}")

@api_router.get("/users/{user_id}/matches", response_model=List[JobMatch])
async def get_job_matches(user_id: str, limit: int = 10):
    """Get job matches for a user"""
    try:
        # Get user's resume embedding
        user_results = resume_collection.get(ids=[user_id], include=['embeddings', 'metadatas'])
        if not user_results['ids']:
            raise HTTPException(status_code=404, detail="User resume not found")
        
        user_embedding = user_results['embeddings'][0]
        user_metadata = user_results['metadatas'][0]
        
        # Get all job embeddings
        job_results = job_collection.get(include=['embeddings', 'metadatas'])
        if not job_results['ids']:
            return []
        
        job_embeddings = np.array(job_results['embeddings'])
        user_embedding_array = np.array(user_embedding).reshape(1, -1)
        
        # Calculate similarity scores
        similarities = cosine_similarity(user_embedding_array, job_embeddings)[0]
        
        # Get top matches
        top_indices = np.argsort(similarities)[::-1][:limit]
        matches = []
        
        for idx in top_indices:
            job_id = job_results['ids'][idx]
            similarity_score = float(similarities[idx])
            job_metadata = job_results['metadatas'][idx]
            
            # Calculate matching skills
            user_skills_raw = user_metadata.get('skills', '[]')
            job_skills_raw = job_metadata.get('requirements', '[]')
            
            # Parse JSON strings back to lists
            try:
                user_skills = set(json.loads(user_skills_raw) if isinstance(user_skills_raw, str) else user_skills_raw)
                job_skills = set(json.loads(job_skills_raw) if isinstance(job_skills_raw, str) else job_skills_raw)
            except (json.JSONDecodeError, TypeError):
                user_skills = set()
                job_skills = set()
            
            matching_skills = list(user_skills.intersection(job_skills))
            
            match = JobMatch(
                user_id=user_id,
                job_id=job_id,
                similarity_score=similarity_score,
                matching_skills=matching_skills,
                match_reasons=[f"Similarity: {similarity_score:.2%}"]
            )
            matches.append(match)
        
        return matches
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting matches: {str(e)}")

@api_router.get("/jobs", response_model=List[JobListing])
async def get_jobs(limit: int = 50):
    """Get all jobs"""
    jobs = await db.jobs.find().limit(limit).to_list(limit)
    return [JobListing(**job) for job in jobs]

@api_router.post("/jobs", response_model=JobListing)
async def create_job(job_data: JobListing):
    """Create a new job listing"""
    # Generate embedding for job description
    job_text = f"{job_data.title} {job_data.description} {' '.join(job_data.requirements)}"
    embedding = embedding_model.encode(job_text)
    
    # Store in vector database
    job_collection.upsert(
        ids=[job_data.id],
        embeddings=[embedding.tolist()],
        metadatas=[{
            "title": job_data.title,
            "company": job_data.company,
            "location": job_data.location,
            "requirements": json.dumps(job_data.requirements),
            "source": job_data.source
        }]
    )
    
    # Store in MongoDB
    await db.jobs.insert_one(job_data.dict())
    return job_data

@api_router.get("/dashboard/{user_id}")
async def get_dashboard_data(user_id: str):
    """Get dashboard data for a user"""
    try:
        # Get user
        user = await db.users.find_one({"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Get recent matches
        matches = await get_job_matches(user_id, limit=5)
        
        # Get application history
        applications = await db.applications.find({"user_id": user_id}).to_list(100)
        
        # Get scraping tasks
        scraping_tasks = await db.scraping_tasks.find({"user_id": user_id}).to_list(10)
        
        # Calculate stats
        total_applications = len(applications)
        successful_applications = len([app for app in applications if app.get('status') == 'applied'])
        success_rate = (successful_applications / total_applications * 100) if total_applications > 0 else 0
        
        return {
            "user": UserProfile(**user),
            "matches": matches,
            "applications": applications,
            "scraping_tasks": scraping_tasks,
            "stats": {
                "total_applications": total_applications,
                "successful_applications": successful_applications,
                "success_rate": round(success_rate, 2),
                "skills_count": len(user.get('skills', [])),
                "experience_years": user.get('experience_years', 0)
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting dashboard data: {str(e)}")

@api_router.post("/scrape/test")
async def test_scraping():
    """Test job scraping functionality"""
    # Sample job data for testing
    sample_jobs = [
        {
            "title": "Software Engineer",
            "company": "TechCorp",
            "location": "San Francisco, CA",
            "description": "We are looking for a skilled software engineer to join our team. Experience with Python, JavaScript, and React required.",
            "requirements": ["python", "javascript", "react", "git"],
            "salary_range": "$80,000 - $120,000",
            "source": "indeed",
            "url": "https://indeed.com/job/123"
        },
        {
            "title": "Full Stack Developer",
            "company": "StartupXYZ",
            "location": "Remote",
            "description": "Full stack developer needed for fast-growing startup. Must know Node.js, React, and MongoDB.",
            "requirements": ["nodejs", "react", "mongodb", "javascript"],
            "salary_range": "$70,000 - $100,000",
            "source": "linkedin",
            "url": "https://linkedin.com/job/456"
        },
        {
            "title": "Data Scientist",
            "company": "DataCorp",
            "location": "New York, NY",
            "description": "Data scientist position requiring Python, pandas, and machine learning expertise.",
            "requirements": ["python", "pandas", "tensorflow", "sql"],
            "salary_range": "$90,000 - $130,000",
            "source": "google",
            "url": "https://google.com/job/789"
        }
    ]
    
    created_jobs = []
    for job_data in sample_jobs:
        job = JobListing(**job_data)
        await create_job(job)
        created_jobs.append(job)
    
    return {
        "message": "Test scraping completed",
        "jobs_created": len(created_jobs),
        "jobs": created_jobs
    }

@api_router.post("/scrape/real")
async def real_scraping(user_id: str, keywords: List[str] = ["software engineer"], location: str = "Remote"):
    """Real job scraping using JobSpy"""
    try:
        from job_scraper import JobScraper
        
        scraper = JobScraper(use_proxies=True, max_results_per_site=50)
        
        # Scrape jobs
        jobs = await scraper.scrape_jobs_by_keywords(keywords, location, max_jobs=50)
        
        # Store jobs in database
        created_jobs = []
        for job_data in jobs:
            job_obj = JobListing(
                title=job_data.get('title', ''),
                company=job_data.get('company', ''),
                location=job_data.get('location', ''),
                description=job_data.get('description', ''),
                requirements=job_data.get('requirements', []),
                salary_range=job_data.get('salary_range', ''),
                job_type=job_data.get('job_type', 'fulltime'),
                source=job_data.get('source', ''),
                url=job_data.get('job_url', '')
            )
            
            await create_job(job_obj)
            created_jobs.append(job_obj)
        
        return {
            "message": "Real scraping completed",
            "jobs_created": len(created_jobs),
            "keywords": keywords,
            "location": location,
            "jobs": created_jobs
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error scraping jobs: {str(e)}")

@api_router.post("/apply/test")
async def test_application(user_id: str, job_id: str):
    """Test job application functionality"""
    try:
        from apply_bot import JobApplicationBot
        
        # Get user and job data
        user = await db.users.find_one({"id": user_id})
        job = await db.jobs.find_one({"id": job_id})
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Prepare user profile
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
            'availability': user.get('availability', 'Immediately')
        }
        
        # Convert job to required format
        job_data = {
            'id': job['id'],
            'job_url': job['url'],
            'title': job['title'],
            'company': job['company'],
            'source': job['source']
        }
        
        # Test application
        async with JobApplicationBot(headless=True) as bot:
            result = await bot.apply_to_job(job_data, user_profile)
        
        # Store application result
        application_record = ApplicationRecord(
            user_id=user_id,
            job_id=job_id,
            status=result.status,
            error_message=result.error_message,
            retry_count=result.retry_count
        )
        
        await db.applications.insert_one(application_record.dict())
        
        return {
            "message": "Test application completed",
            "application_result": {
                "success": result.success,
                "status": result.status,
                "error_message": result.error_message,
                "retry_count": result.retry_count
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error testing application: {str(e)}")

@api_router.post("/scheduler/start")
async def start_scheduler():
    """Start the autonomous scheduler"""
    try:
        from scheduler import AutoApplyScheduler
        
        # This would start the scheduler in a background task
        # For now, return a success message
        return {
            "message": "Scheduler start requested",
            "status": "success",
            "note": "In production, this would start the background scheduler"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting scheduler: {str(e)}")

@api_router.get("/scheduler/status")
async def get_scheduler_status():
    """Get scheduler status and statistics"""
    try:
        # Get recent workflow logs
        recent_logs = await db.workflow_logs.find().sort("created_at", -1).limit(10).to_list(10)
        
        # Get system stats
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_applications = await db.applications.count_documents({
            "applied_at": {"$gte": today}
        })
        
        today_jobs = await db.jobs.count_documents({
            "scraped_at": {"$gte": today}
        })
        
        total_users = await db.users.count_documents({})
        
        return {
            "status": "running",
            "today_stats": {
                "jobs_scraped": today_jobs,
                "applications_sent": today_applications,
                "active_users": total_users
            },
            "recent_logs": recent_logs
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting scheduler status: {str(e)}")

@api_router.get("/applications/{user_id}")
async def get_user_applications(user_id: str, limit: int = 50):
    """Get application history for a user"""
    try:
        applications = await db.applications.find({"user_id": user_id}).sort("applied_at", -1).limit(limit).to_list(limit)
        
        # Get job details for each application
        for app in applications:
            job = await db.jobs.find_one({"id": app["job_id"]})
            if job:
                app["job_details"] = {
                    "title": job.get("title", ""),
                    "company": job.get("company", ""),
                    "location": job.get("location", ""),
                    "source": job.get("source", "")
                }
        
        return applications
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting applications: {str(e)}")

@api_router.get("/jobs/{user_id}")
async def get_user_jobs(user_id: str, limit: int = 100):
    """Get scraped jobs for a user"""
    try:
        jobs = await db.jobs.find({"user_id": user_id}).sort("scraped_at", -1).limit(limit).to_list(limit)
        return jobs
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting jobs: {str(e)}")

@api_router.put("/users/{user_id}/preferences")
async def update_user_preferences(user_id: str, preferences: Dict[str, Any]):
    """Update user job preferences"""
    try:
        # Update user preferences
        await db.users.update_one(
            {"id": user_id},
            {"$set": {
                "job_preferences": preferences,
                "updated_at": datetime.utcnow()
            }}
        )
        
        return {"message": "Preferences updated successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating preferences: {str(e)}")

@api_router.get("/stats/system")
async def get_system_stats():
    """Get overall system statistics"""
    try:
        # Get counts
        total_users = await db.users.count_documents({})
        total_jobs = await db.jobs.count_documents({})
        total_applications = await db.applications.count_documents({})
        successful_applications = await db.applications.count_documents({"status": "applied"})
        
        # Get recent activity
        last_24h = datetime.utcnow() - timedelta(hours=24)
        recent_jobs = await db.jobs.count_documents({"scraped_at": {"$gte": last_24h}})
        recent_applications = await db.applications.count_documents({"applied_at": {"$gte": last_24h}})
        
        # Calculate success rate
        success_rate = (successful_applications / total_applications * 100) if total_applications > 0 else 0
        
        return {
            "total_users": total_users,
            "total_jobs": total_jobs,
            "total_applications": total_applications,
            "successful_applications": successful_applications,
            "success_rate": round(success_rate, 2),
            "last_24h": {
                "jobs_scraped": recent_jobs,
                "applications_sent": recent_applications
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting system stats: {str(e)}")

# AI-powered endpoints
@api_router.post("/ai/apply")
async def ai_apply_to_jobs(request: dict):
    """
    Apply to jobs using AI-powered application bot
    """
    try:
        if not AIJobApplicationBot:
            raise HTTPException(status_code=500, detail="AI application bot not available")
            
        user_id = request.get('user_id')
        job_urls = request.get('job_urls', [])
        
        if not user_id or not job_urls:
            raise HTTPException(status_code=400, detail="user_id and job_urls are required")
        
        # Get user data
        user = await db.users.find_one({"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Prepare user data for AI bot
        user_data = {
            'first_name': user.get('name', '').split()[0] if user.get('name') else '',
            'last_name': ' '.join(user.get('name', '').split()[1:]) if len(user.get('name', '').split()) > 1 else '',
            'email': user.get('email', ''),
            'phone': user.get('phone', ''),
            'resume_text': user.get('resume_text', '')
        }
        
        # Initialize AI bot
        bot = AIJobApplicationBot(headless=True)
        
        try:
            # Apply to jobs
            results = await bot.apply_to_multiple_jobs(job_urls, user_data)
            
            # Store application records
            for result in results:
                application_record = ApplicationRecord(
                    user_id=user_id,
                    job_id=result.job_id,
                    status=result.status,
                    applied_at=result.applied_at,
                    error_message=result.error_message
                )
                await db.applications.insert_one(application_record.dict())
            
            return {
                "message": "AI application process completed",
                "results": [
                    {
                        "job_url": result.job_url,
                        "success": result.success,
                        "status": result.status,
                        "ai_recommendations": result.ai_recommendations
                    }
                    for result in results
                ],
                "success_count": sum(1 for r in results if r.success),
                "total_count": len(results)
            }
            
        finally:
            await bot.close()
            
    except Exception as e:
        logger.error(f"AI application failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/ai/scrape")
async def ai_scrape_jobs(request: dict):
    """
    Scrape jobs using AI-powered scraper with filtering
    """
    try:
        if not AdvancedJobScraper:
            raise HTTPException(status_code=500, detail="AI scraper not available")
            
        keywords = request.get('keywords', '')
        location = request.get('location', 'United States')
        job_boards = request.get('job_boards', ['indeed', 'linkedin', 'glassdoor'])
        user_id = request.get('user_id')
        
        if not keywords:
            raise HTTPException(status_code=400, detail="keywords are required")
        
        # Get user preferences if user_id provided
        user_preferences = None
        if user_id:
            user = await db.users.find_one({"id": user_id})
            if user:
                user_preferences = {
                    'skills': user.get('skills', []),
                    'experience_years': user.get('experience_years', 0)
                }
        
        # Initialize AI scraper
        scraper = AdvancedJobScraper()
        
        # Scrape jobs
        jobs = await scraper.scrape_all_jobs(
            keywords=keywords,
            location=location,
            job_boards=job_boards,
            user_preferences=user_preferences
        )
        
        # Store jobs in database
        for job in jobs:
            job_listing = JobListing(
                id=job['id'],
                title=job['title'],
                company=job['company'],
                location=job['location'],
                description=job['description'],
                requirements=job.get('requirements', []),
                salary_range=f"{job.get('salary_min', '')}-{job.get('salary_max', '')}" if job.get('salary_min') or job.get('salary_max') else None,
                job_type=job.get('job_type', 'full-time'),
                source=job['source'],
                url=job['url'],
                posted_date=job['posted_date'],
                scraped_at=job['scraped_at']
            )
            
            # Store in MongoDB
            await db.jobs.replace_one(
                {"id": job['id']},
                job_listing.dict(),
                upsert=True
            )
            
            # Store in vector database
            embedding = embedding_model.encode(job['description'])
            job_collection.upsert(
                ids=[job['id']],
                embeddings=[embedding.tolist()],
                metadatas=[{
                    'title': job['title'],
                    'company': job['company'],
                    'location': job['location'],
                    'source': job['source'],
                    'ai_score': job.get('ai_score', 0.0)
                }]
            )
        
        return {
            "message": "AI job scraping completed",
            "jobs_found": len(jobs),
            "job_boards": job_boards,
            "keywords": keywords,
            "location": location,
            "ai_filtered": user_preferences is not None,
            "jobs": jobs[:20]  # Return top 20 jobs
        }
        
    except Exception as e:
        logger.error(f"AI scraping failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/ai/optimize-resume")
async def ai_optimize_resume(request: dict):
    """
    Optimize resume using AI for specific job
    """
    try:
        if not AIJobApplicationBot:
            raise HTTPException(status_code=500, detail="AI application bot not available")
            
        user_id = request.get('user_id')
        job_description = request.get('job_description', '')
        
        if not user_id or not job_description:
            raise HTTPException(status_code=400, detail="user_id and job_description are required")
        
        # Get user data
        user = await db.users.find_one({"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        resume_text = user.get('resume_text', '')
        if not resume_text:
            raise HTTPException(status_code=400, detail="User has no resume")
        
        # Initialize AI bot for resume optimization
        bot = AIJobApplicationBot()
        
        try:
            # Optimize resume
            optimized_resume = await bot.ai_optimize_resume(resume_text, job_description)
            
            # Generate cover letter
            cover_letter = await bot.ai_generate_cover_letter(
                resume_text, 
                job_description, 
                request.get('company_name', 'Company')
            )
            
            return {
                "message": "Resume optimization completed",
                "original_resume": resume_text,
                "optimized_resume": optimized_resume,
                "cover_letter": cover_letter,
                "improvement_score": len(optimized_resume) / len(resume_text) if resume_text else 1.0
            }
            
        finally:
            await bot.close()
            
    except Exception as e:
        logger.error(f"Resume optimization failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/ai/job-recommendations/{user_id}")
async def get_ai_job_recommendations(user_id: str):
    """
    Get AI-powered job recommendations for user
    """
    try:
        # Get user data
        user = await db.users.find_one({"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Get user preferences
        user_skills = user.get('skills', [])
        user_experience = user.get('experience_years', 0)
        user_preferences_text = f"Skills: {', '.join(user_skills)}, Experience: {user_experience} years"
        
        # Create user embedding
        user_embedding = embedding_model.encode([user_preferences_text])
        
        # Search for similar jobs in vector database
        results = job_collection.query(
            query_embeddings=[user_embedding[0].tolist()],
            n_results=50
        )
        
        # Get job details from MongoDB
        job_recommendations = []
        for i, job_id in enumerate(results['ids'][0]):
            job = await db.jobs.find_one({"id": job_id})
            if job:
                job['ai_score'] = 1 - results['distances'][0][i]  # Convert distance to similarity
                job_recommendations.append(job)
        
        # Sort by AI score
        job_recommendations.sort(key=lambda x: x['ai_score'], reverse=True)
        
        return {
            "message": "AI job recommendations generated",
            "user_id": user_id,
            "recommendations_count": len(job_recommendations),
            "user_skills": user_skills,
            "user_experience": user_experience,
            "recommendations": job_recommendations[:20]  # Top 20 recommendations
        }
        
    except Exception as e:
        logger.error(f"Job recommendations failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/ai/batch-apply")
async def ai_batch_apply(request: dict):
    """
    Apply to multiple jobs automatically using AI
    """
    try:
        if not AIJobApplicationBot or not AdvancedJobScraper:
            raise HTTPException(status_code=500, detail="AI modules not available")
            
        user_id = request.get('user_id')
        max_applications = request.get('max_applications', 10)
        keywords = request.get('keywords', 'software engineer')
        location = request.get('location', 'United States')
        
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")
        
        # Get user data
        user = await db.users.find_one({"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Get AI job recommendations
        recommendations_response = await get_ai_job_recommendations(user_id)
        recommendations = recommendations_response.get('recommendations', [])
        
        # If no recommendations, scrape new jobs
        if not recommendations:
            scraper = AdvancedJobScraper()
            user_preferences = {
                'skills': user.get('skills', []),
                'experience_years': user.get('experience_years', 0)
            }
            
            jobs = await scraper.scrape_all_jobs(
                keywords=keywords,
                location=location,
                job_boards=['indeed', 'linkedin', 'glassdoor'],
                user_preferences=user_preferences
            )
            
            recommendations = jobs[:max_applications]
        
        # Apply to top recommendations
        job_urls = [job['url'] for job in recommendations[:max_applications]]
        
        # Use AI application bot
        apply_response = await ai_apply_to_jobs({
            'user_id': user_id,
            'job_urls': job_urls
        })
        
        return {
            "message": "AI batch application completed",
            "applications_submitted": apply_response.get('success_count', 0),
            "total_attempted": apply_response.get('total_count', 0),
            "recommendations_used": len(recommendations),
            "results": apply_response.get('results', [])
        }
        
    except Exception as e:
        logger.error(f"Batch application failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Include router
app.include_router(api_router)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()