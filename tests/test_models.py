import pytest
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from src.database import Base
from src.models import User, Job

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
