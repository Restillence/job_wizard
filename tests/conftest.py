import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Optional
from sqlalchemy.pool import StaticPool
from src.database import Base, get_db
from src.main import app
from src.models import (
    User,
    Job,
    Resume,
    Application,
    ApplicationStatus,
    InterviewPrep,
    Company,
    CompanySize,
)

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_user():
    db = TestingSessionLocal()
    db.query(User).filter(User.id == "test_user_id").delete()

    user = User(id="test_user_id", email="test@test.com", hashed_password="pwd")
    db.add(user)
    db.commit()
    yield
    db.query(User).delete()
    db.commit()
    db.close()


def create_test_company(
    db: Session, name: str = "Test Company", url: Optional[str] = None
) -> Company:
    company = db.query(Company).filter(Company.name == name).first()
    if company:
        return company
    company = Company(
        name=name,
        url=url or f"https://{name.lower().replace(' ', '-')}.example.com/careers",
        city="Berlin",
        industry="Tech",
        company_size=CompanySize.startup,
    )
    db.add(company)
    db.commit()
    return company
