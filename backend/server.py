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
    resume_text: str
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
            metadatas=[{"user_id": user_id, "skills": skills, "experience_years": experience_years}]
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
        user_results = resume_collection.get(ids=[user_id])
        if not user_results['ids']:
            raise HTTPException(status_code=404, detail="User resume not found")
        
        user_embedding = user_results['embeddings'][0]
        user_metadata = user_results['metadatas'][0]
        
        # Get all job embeddings
        job_results = job_collection.get()
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
            user_skills = set(user_metadata.get('skills', []))
            job_skills = set(job_metadata.get('requirements', []))
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
            "requirements": job_data.requirements,
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