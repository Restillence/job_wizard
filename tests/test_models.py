import pytest
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError
from src.database import Base
from src.models import (
    User,
    Job,
    Resume,
    Application,
    ApplicationStatus,
    InterviewPrep,
    Company,
    CompanySize,
    UserSearch,
)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()


def create_company(session: Session, name: str = "Test Inc") -> Company:
    company = Company(
        name=name,
        url=f"https://{name.lower().replace(' ', '-')}.com/careers",
    )
    session.add(company)
    session.commit()
    return company


class TestUser:
    def test_create_user(self, db_session: Session) -> None:
        user = User(email="test@example.com", hashed_password="hashed")
        db_session.add(user)
        db_session.commit()
        assert user.id is not None
        assert user.email == "test@example.com"
        assert user.zusatz_infos == {}

    def test_user_email_unique_constraint(self, db_session: Session) -> None:
        user1 = User(email="same@example.com", hashed_password="pwd1")
        user2 = User(email="same@example.com", hashed_password="pwd2")
        db_session.add_all([user1, user2])
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_user_defaults(self, db_session: Session) -> None:
        user = User(email="defaults@example.com", hashed_password="pwd")
        db_session.add(user)
        db_session.commit()
        assert user.subscription_tier == "free"
        assert user.payment_customer_id is None
        assert user.credits_used == 0
        assert user.credits_limit == 10
        assert user.is_superuser is False
        assert user.created_at is not None
        assert user.last_reset_date is not None

    def test_superuser_flag(self, db_session: Session) -> None:
        admin = User(
            email="admin@example.com", hashed_password="pwd", is_superuser=True
        )
        db_session.add(admin)
        db_session.commit()
        assert admin.is_superuser is True


class TestCompany:
    def test_create_company(self, db_session: Session) -> None:
        company = Company(
            name="TechCorp",
            city="Berlin",
            industry="Software",
            company_size=CompanySize.startup,
            url="https://techcorp.example.com/careers",
        )
        db_session.add(company)
        db_session.commit()
        assert company.id is not None
        assert company.name == "TechCorp"
        assert company.company_size == CompanySize.startup

    def test_company_url_unique(self, db_session: Session) -> None:
        c1 = Company(name="C1", url="https://unique.example.com/careers")
        c2 = Company(name="C2", url="https://unique.example.com/careers")
        db_session.add_all([c1, c2])
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestJob:
    def test_create_job(self, db_session: Session) -> None:
        company = create_company(db_session)
        job = Job(
            source_url="http://test.com",
            title="Dev",
            company_id=company.id,
            description="Desc",
        )
        db_session.add(job)
        db_session.commit()
        assert job.id is not None
        assert job.extracted_requirements == {}
        assert job.is_active is True
        assert job.first_seen_at is not None
        assert job.last_seen_at is not None

    def test_job_source_url_not_unique(self, db_session: Session) -> None:
        company = create_company(db_session)
        job1 = Job(
            source_url="http://same-url.com",
            title="Dev",
            company_id=company.id,
            description="Desc",
            dedup_hash="hash_a",
        )
        job2 = Job(
            source_url="http://same-url.com",
            title="Dev2",
            company_id=company.id,
            description="Desc2",
            dedup_hash="hash_b",
        )
        db_session.add_all([job1, job2])
        db_session.commit()
        assert job1.id != job2.id

    def test_job_dedup_hash_unique(self, db_session: Session) -> None:
        company = create_company(db_session)
        job1 = Job(
            source_url="http://first.com",
            title="Dev",
            company_id=company.id,
            description="Desc",
            dedup_hash="same_hash",
        )
        db_session.add(job1)
        db_session.commit()
        job2 = Job(
            source_url="http://second.com",
            title="Dev2",
            company_id=company.id,
            description="Desc2",
            dedup_hash="same_hash",
        )
        db_session.add(job2)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_job_company_relationship(self, db_session: Session) -> None:
        company = create_company(db_session, "RelCorp")
        job = Job(
            source_url="http://rel.com",
            title="Dev",
            company_id=company.id,
            description="Desc",
        )
        db_session.add(job)
        db_session.commit()

        assert job.company is not None
        assert job.company.name == "RelCorp"


class TestApplication:
    def test_create_application(self, db_session: Session) -> None:
        user = User(email="app@example.com", hashed_password="pwd")
        company = create_company(db_session)
        job = Job(
            source_url="http://app.com",
            title="Dev",
            company_id=company.id,
            description="Desc",
        )
        db_session.add_all([user, job])
        db_session.commit()

        app = Application(user_id=user.id, job_id=job.id)
        db_session.add(app)
        db_session.commit()

        assert app.id is not None
        assert app.status == ApplicationStatus.Drafted
        assert app.ai_match_rationale is None
        assert app.cover_letter_file_path is None
        assert app.similarity_score is None

    def test_application_status_transitions(self, db_session: Session) -> None:
        user = User(email="status@example.com", hashed_password="pwd")
        company = create_company(db_session)
        job = Job(
            source_url="http://status.com",
            title="Dev",
            company_id=company.id,
            description="Desc",
        )
        db_session.add_all([user, job])
        db_session.commit()

        app = Application(
            user_id=user.id, job_id=job.id, status=ApplicationStatus.Drafted
        )
        db_session.add(app)
        db_session.commit()

        assert app.status == ApplicationStatus.Drafted

        app.status = ApplicationStatus.Approved
        db_session.commit()
        assert app.status == ApplicationStatus.Approved

        app.status = ApplicationStatus.Sent
        db_session.commit()
        assert app.status == ApplicationStatus.Sent

    def test_application_updated_at_changes(self, db_session: Session) -> None:
        user = User(email="updated@example.com", hashed_password="pwd")
        company = create_company(db_session)
        job = Job(
            source_url="http://updated.com",
            title="Dev",
            company_id=company.id,
            description="Desc",
        )
        db_session.add_all([user, job])
        db_session.commit()

        app = Application(user_id=user.id, job_id=job.id)
        db_session.add(app)
        db_session.commit()
        original_updated = app.updated_at

        app.status = ApplicationStatus.Approved
        db_session.commit()

        assert app.updated_at >= original_updated

    def test_application_with_ai_rationale(self, db_session: Session) -> None:
        user = User(email="rationale@example.com", hashed_password="pwd")
        company = create_company(db_session)
        job = Job(
            source_url="http://rationale.com",
            title="Dev",
            company_id=company.id,
            description="Desc",
        )
        db_session.add_all([user, job])
        db_session.commit()

        app = Application(
            user_id=user.id,
            job_id=job.id,
            ai_match_rationale="Strong Python skills match requirements",
            similarity_score=0.87,
        )
        db_session.add(app)
        db_session.commit()

        assert app.ai_match_rationale == "Strong Python skills match requirements"
        assert app.similarity_score == 0.87


class TestResume:
    def test_create_resume(self, db_session: Session) -> None:
        user = User(email="resume@example.com", hashed_password="pwd")
        db_session.add(user)
        db_session.commit()

        resume = Resume(user_id=user.id, file_path="uploads/resumes/test.pdf")
        db_session.add(resume)
        db_session.commit()

        assert resume.id is not None
        assert resume.file_path == "uploads/resumes/test.pdf"
        assert resume.created_at is not None
        assert resume.embedding is None


class TestInterviewPrep:
    def test_create_interview_prep(self, db_session: Session) -> None:
        user = User(email="prep@example.com", hashed_password="pwd")
        company = create_company(db_session)
        job = Job(
            source_url="http://prep.com",
            title="Dev",
            company_id=company.id,
            description="Desc",
        )
        db_session.add_all([user, job])
        db_session.commit()

        prep = InterviewPrep(
            user_id=user.id, job_id=job.id, content="Focus on Python and SQL"
        )
        db_session.add(prep)
        db_session.commit()

        assert prep.id is not None
        assert prep.content == "Focus on Python and SQL"


class TestRelationships:
    def test_user_has_multiple_resumes(self, db_session: Session) -> None:
        user = User(email="multi@example.com", hashed_password="pwd")
        db_session.add(user)
        db_session.commit()

        resume1 = Resume(user_id=user.id, file_path="uploads/r1.pdf")
        resume2 = Resume(user_id=user.id, file_path="uploads/r2.pdf")
        db_session.add_all([resume1, resume2])
        db_session.commit()

        result = db_session.query(Resume).filter(Resume.user_id == user.id).all()
        assert len(result) == 2

    def test_user_has_multiple_applications(self, db_session: Session) -> None:
        user = User(email="apps@example.com", hashed_password="pwd")
        company = create_company(db_session)
        job1 = Job(
            source_url="http://job1.com",
            title="Dev1",
            company_id=company.id,
            description="D1",
        )
        job2 = Job(
            source_url="http://job2.com",
            title="Dev2",
            company_id=company.id,
            description="D2",
        )
        db_session.add_all([user, job1, job2])
        db_session.commit()

        app1 = Application(user_id=user.id, job_id=job1.id)
        app2 = Application(user_id=user.id, job_id=job2.id)
        db_session.add_all([app1, app2])
        db_session.commit()

        result = (
            db_session.query(Application).filter(Application.user_id == user.id).all()
        )
        assert len(result) == 2

    def test_company_has_multiple_jobs(self, db_session: Session) -> None:
        company = Company(
            name="MultiJobCorp", url="https://multijob.example.com/careers"
        )
        db_session.add(company)
        db_session.commit()

        job1 = Job(
            source_url="http://mj1.com",
            title="Job1",
            company_id=company.id,
            description="D1",
        )
        job2 = Job(
            source_url="http://mj2.com",
            title="Job2",
            company_id=company.id,
            description="D2",
        )
        db_session.add_all([job1, job2])
        db_session.commit()

        assert len(company.jobs) == 2


class TestUserSearch:
    def test_create_user_search(self, db_session: Session) -> None:
        user = User(email="search@example.com", hashed_password="pwd")
        db_session.add(user)
        db_session.commit()

        search = UserSearch(
            user_id=user.id,
            cities=["Berlin", "Munich"],
            industries=["AI", "FinTech"],
            keywords=["Python", "FastAPI"],
            company_size="startup",
        )
        db_session.add(search)
        db_session.commit()

        assert search.id is not None
        assert search.cities == ["Berlin", "Munich"]
        assert search.industries == ["AI", "FinTech"]
        assert search.keywords == ["Python", "FastAPI"]
        assert search.company_size == "startup"
        assert search.created_at is not None

    def test_user_has_multiple_searches(self, db_session: Session) -> None:
        user = User(email="multisearch@example.com", hashed_password="pwd")
        db_session.add(user)
        db_session.commit()

        search1 = UserSearch(
            user_id=user.id,
            cities=["Berlin"],
            industries=["AI"],
        )
        search2 = UserSearch(
            user_id=user.id,
            cities=["Munich"],
            industries=["FinTech"],
        )
        db_session.add_all([search1, search2])
        db_session.commit()

        result = (
            db_session.query(UserSearch).filter(UserSearch.user_id == user.id).all()
        )
        assert len(result) == 2
