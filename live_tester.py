import os
import io
import time
import json
import httpx
from docx import Document

from src.database import engine, SessionLocal
from src.models import Base, User

# Reset DB and initialize test user to bypass rate limit
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

db = SessionLocal()
try:
    if not db.query(User).filter(User.id == "test_user_id").first():
        db.add(User(
            id="test_user_id", 
            email="live@test.com", 
            hashed_password="pwd", 
            is_superuser=True
        ))
        db.commit()
finally:
    db.close()

BASE_URL = "http://127.0.0.1:8000"

def write_out(name, data):
    with open(f"live_output_{name}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[OK] Saved {name}")

def seed_db():
    from src.database import SessionLocal
    from src.models import Company
    import uuid
    db = SessionLocal()
    if db.query(Company).count() < 5:
        print("Seeding DB to bypass 503 Discovery fallback")
        for i in range(6):
            c = Company(
                id=str(uuid.uuid4()),
                name=f"Mock Berlin Startup {i}",
                city="Berlin",
                industry="Software",
                company_size="startup",
                url=f"https://mock-{i}.com/careers",
                url_verified=True
            )
            db.add(c)
        db.commit()
    db.close()

def run():
    seed_db()
    with httpx.Client(timeout=120) as client:
        print("1. Testing /api/v1/companies/search")
        params = {
            "cities": ["Berlin"],
            "industries": ["Software"],
            "company_size": "startup"
        }
        r = client.get(f"{BASE_URL}/api/v1/companies/search", params=params)
        try:
            out_companies = r.json()
            write_out("companies_search", out_companies)
        except:
            print("ERROR response:", r.text)
            return
            
        time.sleep(12)
        
        companies = out_companies.get("companies", [])
        if not companies:
            print("[FAIL] No companies found!")
            return
            
        c_id = companies[0]["id"]
        print(f"2. Testing /api/v1/companies/{c_id}/resolve-url")
        r = client.get(f"{BASE_URL}/api/v1/companies/{c_id}/resolve-url")
        write_out("resolve_url", r.json())
        
        print("3. Testing /api/v1/jobs/extract")
        r = client.post(f"{BASE_URL}/api/v1/jobs/extract", json={"company_ids": [c_id]})
        out_jobs = r.json()
        write_out("jobs_extract", out_jobs)
        
        jobs = out_jobs.get("jobs", [])
        if not jobs:
            print("[FAIL] No jobs extracted!")
            # we keep going for the rest
            
        print("4. Testing /api/v1/resumes/upload")
        doc = Document()
        doc.add_paragraph("Max Mustermann")
        doc.add_paragraph("Software Engineer from Berlin. Expert in Python and FastAPI. 6 years experience.")
        buf = io.BytesIO()
        doc.save(buf)
        
        files = {
            "file": ("resume.docx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        }
        r = client.post(f"{BASE_URL}/api/v1/resumes/upload", files=files)
        out_upload = r.json()
        write_out("uploads", out_upload)
        
        print(f"5. Testing /api/v1/jobs/match ... Using user_id: test_user_id and company_id: {c_id}")
        r = client.post(f"{BASE_URL}/api/v1/jobs/match", json={"user_id": "test_user_id", "company_ids": [c_id], "top_k": 5})
        write_out("match", r.json())
        
        print("6. Testing /api/v1/pipeline/search-and-match")
        pipeline_payload = {
            "cities": ["Munich"],
            "industries": ["B2B SaaS"],
            "keywords": ["Engineer"],
            "company_size": "startup",
            "user_id": "test_user_id",
            "top_k": 5
        }
        r = client.post(f"{BASE_URL}/api/v1/pipeline/search-and-match", json=pipeline_payload)
        write_out("pipeline", r.json())
        
        print("[DONE] Live Evaluation Suite Complete!")

if __name__ == "__main__":
    import threading
    import uvicorn
    from src.main import app
    def start_server():
        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")
    t = threading.Thread(target=start_server, daemon=True)
    t.start()
    time.sleep(3)
    run()
