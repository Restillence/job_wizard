import pytest
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError
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


class TestJob:
    def test_create_job(self, db_session: Session) -> None:
        job = Job(
            source_url="http://test.com",
            title="Dev",
            company="Test Inc",
            description="Desc",
        )
        db_session.add(job)
        db_session.commit()
        assert job.id is not None
        assert job.extracted_requirements == {}

    def test_job_source_url_unique(self, db_session: Session) -> None:
        job1 = Job(
            source_url="http://unique.com",
            title="Dev",
            company="Inc",
            description="Desc",
        )
        job2 = Job(
            source_url="http://unique.com",
            title="Dev2",
            company="Inc2",
            description="Desc2",
        )
        db_session.add_all([job1, job2])
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestApplication:
    def test_create_application(self, db_session: Session) -> None:
        user = User(email="app@example.com", hashed_password="pwd")
        job = Job(
            source_url="http://app.com", title="Dev", company="Inc", description="Desc"
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

    def test_application_status_transitions(self, db_session: Session) -> None:
        user = User(email="status@example.com", hashed_password="pwd")
        job = Job(
            source_url="http://status.com",
            title="Dev",
            company="Inc",
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
        job = Job(
            source_url="http://updated.com",
            title="Dev",
            company="Inc",
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
        job = Job(
            source_url="http://rationale.com",
            title="Dev",
            company="Inc",
            description="Desc",
        )
        db_session.add_all([user, job])
        db_session.commit()

        app = Application(
            user_id=user.id,
            job_id=job.id,
            ai_match_rationale="Strong Python skills match requirements",
        )
        db_session.add(app)
        db_session.commit()

        assert app.ai_match_rationale == "Strong Python skills match requirements"


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


class TestInterviewPrep:
    def test_create_interview_prep(self, db_session: Session) -> None:
        user = User(email="prep@example.com", hashed_password="pwd")
        job = Job(
            source_url="http://prep.com", title="Dev", company="Inc", description="Desc"
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
        job1 = Job(
            source_url="http://job1.com", title="Dev1", company="Inc", description="D1"
        )
        job2 = Job(
            source_url="http://job2.com", title="Dev2", company="Inc", description="D2"
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
