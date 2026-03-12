# JobWiz Phase 2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Scaffolding, DB connection (Multi-Tenant), stateless file storage setup, and basic health check.

**Architecture:** API-first, Synchronous-First/Scale-Later methodology. Database is PostgreSQL via SQLAlchemy 2.0.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy 2.0, Pydantic 2.0, PostgreSQL, Pytest.

---

### Task 1: Project Setup and Dependencies

**Files:**
- Create: `requirements.txt`
- Create: `src/__init__.py`
- Create: `src/main.py`
- Create: `tests/__init__.py`
- Create: `tests/test_main.py`
- Create: `uploads/.gitkeep`
- Create: `uploads/resumes/.gitkeep`
- Create: `uploads/cover_letters/.gitkeep`

**Step 1: Write the failing test**
```python
# tests/test_main.py
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

**Step 2: Create directories and requirements**
Run: `mkdir -p src tests uploads/resumes uploads/cover_letters`
Run: `touch src/__init__.py tests/__init__.py uploads/.gitkeep uploads/resumes/.gitkeep uploads/cover_letters/.gitkeep`
Run: `echo "fastapi\nuvicorn\nsqlalchemy\npydantic\npsycopg2-binary\nalembic\npytest\nhttpx" > requirements.txt`

**Step 3: Write minimal implementation**
```python
# src/main.py
from fastapi import FastAPI

app = FastAPI(title="JobWiz API", version="0.1.0")

@app.get("/health")
def health_check():
    return {"status": "ok"}
```

**Step 4: Run test to verify it passes**
Run: `pytest tests/test_main.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add src/ tests/ uploads/ requirements.txt
git commit -m "chore: setup project structure, directories and health check"
```

### Task 2: Database Configuration

**Files:**
- Create: `src/database.py`
- Create: `src/config.py`
- Create: `tests/test_database.py`

**Step 1: Write the config and failing test**
```python
# src/config.py
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./jobwiz_test.db")

settings = Settings()
```

```python
# tests/test_database.py
from sqlalchemy import text
from src.database import engine, get_db

def test_database_connection():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        assert result.scalar() == 1
```

**Step 2: Write minimal implementation**
```python
# src/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from src.config import settings

# Use connect_args for SQLite (which we use for testing by default if no PG URL provided)
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

**Step 3: Run test to verify it passes**
Run: `pytest tests/test_database.py -v`
Expected: PASS

**Step 4: Commit**
```bash
git add src/config.py src/database.py tests/test_database.py
git commit -m "feat: setup database connection and configuration"
```

### Task 3: Database Models (Users & Jobs)

**Files:**
- Create: `src/models.py`
- Create: `tests/test_models.py`

**Step 1: Write the failing test**
```python
# tests/test_models.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database import Base
from src.models import User, Job
from datetime import datetime

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_create_user(db_session):
    user = User(email="test@example.com", hashed_password="hashed")
    db_session.add(user)
    db_session.commit()
    assert user.id is not None
    assert user.email == "test@example.com"
    assert user.zusatz_infos == {}

def test_create_job(db_session):
    job = Job(source_url="http://test.com", title="Dev", company="Test Inc", description="Desc")
    db_session.add(job)
    db_session.commit()
    assert job.id is not None
    assert job.extracted_requirements == {}
```

**Step 2: Write minimal implementation**
```python
# src/models.py
import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, JSON, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from src.database import Base

def get_utc_now():
    return datetime.now(timezone.utc)

def generate_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=get_utc_now)
    zusatz_infos = Column(JSON, default=dict)

class Job(Base):
    __tablename__ = "jobs"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    source_url = Column(String, unique=True, nullable=False)
    title = Column(String, nullable=False)
    company = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    extracted_requirements = Column(JSON, default=dict)
    created_at = Column(DateTime, default=get_utc_now)
```

**Step 3: Run test to verify it passes**
Run: `pytest tests/test_models.py -v`
Expected: PASS

**Step 4: Commit**
```bash
git add src/models.py tests/test_models.py
git commit -m "feat: add user and job database models"
```

### Task 4: Database Models (Multi-Tenant Entities)

**Files:**
- Modify: `src/models.py`
- Modify: `tests/test_models.py`

**Step 1: Write the failing test**
```python
# Append to tests/test_models.py
from src.models import Resume, Application, ApplicationStatus, InterviewPrep

def test_create_multi_tenant_entities(db_session):
    user = User(email="test2@example.com", hashed_password="pwd")
    job = Job(source_url="http://test2.com", title="Dev", company="Inc", description="Desc")
    db_session.add_all([user, job])
    db_session.commit()
    
    resume = Resume(user_id=user.id, file_path="uploads/resumes/1.pdf")
    app = Application(user_id=user.id, job_id=job.id, status=ApplicationStatus.Drafted, ai_match_rationale="Good fit")
    prep = InterviewPrep(user_id=user.id, job_id=job.id, content="Tips")
    
    db_session.add_all([resume, app, prep])
    db_session.commit()
    
    assert resume.id is not None
    assert app.status == ApplicationStatus.Drafted
    assert prep.content == "Tips"
```

**Step 2: Write minimal implementation**
```python
# Append to src/models.py

class ApplicationStatus(str, enum.Enum):
    Drafted = "Drafted"
    Approved = "Approved"
    Sent = "Sent"
    Interviewing = "Interviewing"
    Rejected = "Rejected"

class Resume(Base):
    __tablename__ = "resumes"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    file_path = Column(String, nullable=False)
    created_at = Column(DateTime, default=get_utc_now)

class Application(Base):
    __tablename__ = "applications"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)
    status = Column(Enum(ApplicationStatus), default=ApplicationStatus.Drafted, nullable=False)
    ai_match_rationale = Column(Text)
    cover_letter_file_path = Column(String)
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

class InterviewPrep(Base):
    __tablename__ = "interview_prep"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=get_utc_now)
```

**Step 3: Run test to verify it passes**
Run: `pytest tests/test_models.py -v`
Expected: PASS

**Step 4: Commit**
```bash
git add src/models.py tests/test_models.py
git commit -m "feat: add multi-tenant entity models"
```
