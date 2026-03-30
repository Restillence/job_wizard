import asyncio
import os
import uuid
from src.database import SessionLocal
from src.models import User, Resume, Job, Company, CompanySize
from src.services.job_discovery import JobDiscoveryService
from src.services.hybrid_extraction import HybridExtractionService
from src.services.embeddings import generate_resume_embedding, embedding_to_json, json_to_embedding, cosine_similarity

async def main():
    print("Initializing Database Session...")
    db = SessionLocal()

    # 1. Setup Mock User & Resume
    user_id = str(uuid.uuid4())
    user = User(id=user_id, email=f"live_test_{user_id}@test.com", hashed_password="pwd")
    db.add(user)
    db.commit()
    print(f"Created User: {user_id}")

    resume_text = "I am a Senior Python Developer with 5 years of experience in AI, Machine Learning, and Data Science. I know FastAPI, Docker, and PostgreSQL. I am looking for a senior backend or data science role."
    os.makedirs("uploads/resumes", exist_ok=True)
    resume_path = f"uploads/resumes/{user_id}.txt"
    with open(resume_path, "w") as f:
        f.write(resume_text)
    
    print("\nGenerating AI embedding for the user's resume...")
    embedding = generate_resume_embedding(resume_text, {})
    if not embedding:
        print("Failed to generate resume embedding. Check ZAI API key.")
        return

    resume = Resume(
        id=str(uuid.uuid4()),
        user_id=user_id,
        file_path=resume_path,
        embedding=embedding_to_json(embedding)
    )
    db.add(resume)
    db.commit()
    print("Resume vectorized and saved.")

    # 2. Pipeline Parameters
    cities = ["Munich"]
    industries = ["Data Science"]
    keywords = []
    top_k = 5
    
    print(f"\nStarting Pipeline: Cities={cities}, Industries={industries}, Keywords={keywords}")
    
    # Step A: Discovery
    print("\n--- Step A: Job Discovery ---")
    discovery_service = JobDiscoveryService()
    companies_result = await discovery_service.search_companies(
        db=db,
        user_id=user_id,
        cities=cities,
        industries=industries,
        keywords=keywords
    )
    print(f"Discovered Companies: {companies_result.total_found} (New: {companies_result.newly_added})")
    company_ids = [c["id"] for c in companies_result.companies]

    if not company_ids:
        print("No companies found.")
        return

    # Step B: Extraction
    print("\n--- Step B: Job Extraction (Web Scraping & ATS APIs) ---")
    extraction_service = HybridExtractionService()
    jobs_result = await extraction_service.extract_jobs_for_companies(db, company_ids, target_cities=cities)
    print(f"Extracted Jobs: {jobs_result['total_extracted']} (New: {jobs_result['total_new']})")

    # Step C: Matching
    print("\n--- Step C: Vector Matching ---")
    resume_embedding = json_to_embedding(resume.embedding)
    jobs_query = db.query(Job).filter(Job.is_active == True).filter(Job.company_id.in_(company_ids))
    jobs = jobs_query.all()
    
    job_scores = []
    for job in jobs:
        job_embedding = json_to_embedding(job.embedding)
        if job_embedding:
            score = cosine_similarity(resume_embedding, job_embedding)
            job_scores.append((job, score))

    job_scores.sort(key=lambda x: x[1], reverse=True)
    top_jobs = job_scores[:top_k]

    print("\n======================================================================")
    print("PIPELINE RESULTS: TOP MATCHED JOBS FOR USER")
    print("======================================================================")
    for i, (job, score) in enumerate(top_jobs, 1):
        company_name = job.company.name if job.company else "Unknown"
        print(f"{i}. [{score*100:.1f}% Match] {job.title}")
        print(f"   Company: {company_name}")
        print(f"   Link: {job.source_url}")
        print()

    # Cleanup (Optional)
    # db.delete(resume)
    # db.delete(user)
    # db.commit()
    db.close()

if __name__ == "__main__":
    asyncio.run(main())
