import sys
from src.database import SessionLocal
from src.models import Job
from src.services.embeddings import generate_job_embedding, embedding_to_json

def backfill():
    db = SessionLocal()
    jobs_without_embeddings = db.query(Job).filter(Job.embedding.is_(None)).all()
    print(f"Found {len(jobs_without_embeddings)} jobs without embeddings.")
    
    updated = 0
    for job in jobs_without_embeddings:
        print(f"Processing Job ID: {job.id}")
        emb = generate_job_embedding(
            title=job.title,
            description=job.description or "",
            requirements=job.extracted_requirements or {"requirements": []},
            benefits=job.extracted_requirements.get("benefits", []) if job.extracted_requirements else None,
            tags=job.tags
        )
        if emb:
            job.embedding = embedding_to_json(emb)
            updated += 1
            
    db.commit()
    db.close()
    print(f"Successfully generated embeddings for {updated} jobs.")

if __name__ == "__main__":
    backfill()
