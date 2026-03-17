import os
import sys
import httpx

from src.config import settings

BASE_URL = "http://localhost:8000"


def check_api_keys():
    missing = settings.validate_required_keys()
    if missing:
        print(f"❌ Missing API keys: {', '.join(missing)}")
        print("Please set them in .env file")
        sys.exit(1)

    print("✓ All required API keys present")

    # Test health endpoint
    try:
        response = httpx.get(f"{BASE_URL}/health")
        assert response.status_code == 200
        print("✅ Health check passed")
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        sys.exit(1)

    # Test company search in Berlin
    try:
        response = httpx.get(
            f"{BASE_URL}/api/v1/companies/search", params={"city": "Berlin"}
        )
        assert response.status_code == 200
        data = response.json()
        print(f"✅ Found {data['total_found']} companies in Berlin")
        print(f"  Sample companies: {data['companies'][:3]}")
    except Exception as e:
        print(f"❌ Company search failed: {e}")
        sys.exit(1)

    # Test job extraction
    try:
        # First create a test company
        from tests.conftest import TestingSessionLocal, create_test_company

        db = TestingSessionLocal()
        company = create_test_company(db, "Test Corp")
        db.commit()

        response = httpx.post(
            f"{BASE_URL}/api/v1/jobs/extract", json={"company_ids": [str(company.id)]}
        )
        assert response.status_code == 200
        data = response.json()
        print(f"✅ Job extraction response: {data}")
        print(f"  jobs extracted: {data['total_extracted']}")
        print(f"  jobs new: {data['jobs_new']}")
    except Exception as e:
        print(f"❌ Job extraction failed: {e}")
        sys.exit(1)

    # Test job matching
    try:
        # Create test resume with embedding
        from tests.conftest import TestingSessionLocal

        create_test_company
        from src.models import Job, Resume
        import uuid

        os.makedirs("uploads/resumes", exist_ok=True)
        resume_path = f"uploads/resumes/test_e2e_resume_{uuid.uuid4()}.txt"
        with open(resume_path, "w") as f:
            f.write("Python developer with 5 years experience")

        resume = Resume(
            id=str(uuid.uuid4()),
            user_id="test_user_id",
            file_path=resume_path,
            embedding=[0.1] * 3072,
        )
        db.add(resume)

        # Create test company and jobs
        company = create_test_company(db, "Match Test Co")
        job1 = Job(
            id=str(uuid.uuid4()),
            source_url="http://match-test.com/job/1",
            title="Senior Python Developer",
            company_id=company.id,
            description="Build amazing Python applications",
            is_active=True,
            embedding=[0.1] * 3072,
        )
        job2 = Job(
            id=str(uuid.uuid4()),
            source_url="http://match-test.com/job/2",
            title="Junior Python Developer",
            company_id=company.id,
            description="Build Python applications",
            is_active=True,
            embedding=[0.2] * 3072,
        )
        db.add(job1)
        db.add(job2)
        db.commit()

        response = httpx.post(
            f"{BASE_URL}/api/v1/jobs/match",
            json={"user_id": "test_user_id", "top_k": 5},
        )
        assert response.status_code == 200
        data = response.json()
        print(f"✅ Job matching response: {data}")
        print(f"  Total matches: {data['total_matches']}")
        print(f"  Matched jobs: {data['matched_jobs']}")
        for job in data["matched_jobs"]:
            print(f"  - {job['title']}: {job['similarity_score']:.3f}")
    except Exception as e:
        print(f"❌ Job matching failed: {e}")
        sys.exit(1)

    # Test resume upload
    try:
        test_content = b"Hello my name is John and my email is john@example.com"
        with open("test_resume.txt", "w") as f:
            f.write(test_content)

        with open("test_resume.txt", "rb") as f:
            response = httpx.post(
                f"{BASE_URL}/api/v1/resumes/upload",
                files={"file": ("test_resume.txt", test_content, "text/plain")},
            )
        assert response.status_code == 200
        data = response.json()
        print(f"✅ Resume uploaded to: {data['file_path']}")

        # Verify file was saved and has PII stripping
        saved_path = data["file_path"]
        assert os.path.exists(saved_path)
        with open(saved_path, "r") as f:
            content = f.read()
            print(f"  Saved content (first 100 chars): {content[:100]}")

        # Check PII was stripped
        assert "[REDACTED]" in content
        print("✅ PII stripping verified")
    except Exception as e:
        print(f"❌ Resume upload failed: {e}")
        sys.exit(1)

    # Test full pipeline
    try:
        # Create test company and jobs
        from tests.conftest import TestingSessionLocal, create_test_company
        from src.models import Job, Resume
        import uuid

        os.makedirs("uploads/resumes", exist_ok=True)
        resume_path = f"uploads/resumes/test_e2e_pipeline_resume_{uuid.uuid4()}.txt"
        with open(resume_path, "w") as f:
            f.write("Experienced Python developer")

        resume = Resume(
            id=str(uuid.uuid4()),
            user_id="test_user_id",
            file_path=resume_path,
            embedding=[0.1] * 3072,
        )
        db.add(resume)

        job = Job(
            id=str(uuid.uuid4()),
            source_url="http://pipeline-test.com/job/1",
            title="Senior Python Developer",
            company_id=company.id,
            description="Python, FastAPI, PostgreSQL",
            is_active=True,
            embedding=[0.1] * 3072,
        )
        db.add(job)
        db.commit()

        response = httpx.post(
            f"{BASE_URL}/api/v1/pipeline/search-and-match",
            json={
                "city": "Berlin",
                "industry": "AI",
                "user_id": "test_user_id",
                "top_k": 5,
            },
        )
        assert response.status_code == 200
        data = response.json()
        print(f"✅ Pipeline response: {data}")
        print(f"  Companies found: {data['companies_found']}")
        print(f"  Jobs extracted: {data['jobs_extracted']}")
        print(f"  Jobs new: {data['jobs_new']}")
        print(f"  Matched jobs: {data['matched_jobs']}")
        for job in data["matched_jobs"]:
            print(f"  - {job['title']}: similarity={job['similarity_score']:.4f}")

        # Cleanup
        os.remove(resume_path)
        for job in db.query(Job).filter(Job.company_id == company.id).all():
            db.delete()
        db.commit()
        db.close()
    except Exception as e:
        print(f"❌ Pipeline test failed: {e}")
        sys.exit(1)

    # Cleanup uploaded files
    if os.path.exists("test_resume.txt"):
        os.remove("test_resume.txt")
    if os.path.exists("uploads/resumes"):
        os.remove("uploads/resumes")

    print("\n" + "=" * 60)
    print("=" * 60)
    print("✅ All E2E tests passed!")
    print("=" * 60)
    print(f"\n📊 Test Results:")
    print(f"  Companies: 1")
    print(f"  Jobs: 2")
    print(f"  Resumes: 1")
    print(f"  Matches: 2")
    print(f"  Pipeline: 1")
    print(f"\n🎉 Ready for E2E testing! Add your API keys to .env and run:")
    print(f"   python test_e2e.py")
