import pytest
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from src.database import Base
from src.models import User, Job, Resume, Application, ApplicationStatus, InterviewPrep

@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()

def test_create_user(db_session: Session) -> None:
    user = User(email="test@example.com", hashed_password="hashed")
    db_session.add(user)
    db_session.commit()
    assert user.id is not None
    assert user.email == "test@example.com"
    assert user.zusatz_infos == {}

def test_create_job(db_session: Session) -> None:
    job = Job(source_url="http://test.com", title="Dev", company="Test Inc", description="Desc")
    db_session.add(job)
    db_session.commit()
    assert job.id is not None
    assert job.extracted_requirements == {}

def test_create_multi_tenant_entities(db_session: Session) -> None:
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
