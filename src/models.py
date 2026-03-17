import uuid
import enum
from typing import Any, Optional
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, JSON, ForeignKey, Enum, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base


def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generate_uuid() -> str:
    return str(uuid.uuid4())


class CompanySize(str, enum.Enum):
    startup = "startup"
    hidden_champion = "hidden_champion"
    enterprise = "enterprise"


class ApplicationStatus(str, enum.Enum):
    Drafted = "Drafted"
    Approved = "Approved"
    Sent = "Sent"
    Rejected = "Rejected"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now
    )
    zusatz_infos: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    subscription_tier: Mapped[str] = mapped_column(String, default="free")
    payment_customer_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    credits_used: Mapped[int] = mapped_column(default=0)
    credits_limit: Mapped[int] = mapped_column(default=10)
    last_reset_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now
    )
    is_superuser: Mapped[bool] = mapped_column(default=False)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String, index=True)
    city: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    company_size: Mapped[Optional[CompanySize]] = mapped_column(
        Enum(CompanySize), nullable=True
    )
    url: Mapped[str] = mapped_column(String, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now
    )

    jobs: Mapped[list["Job"]] = relationship(back_populates="company")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    company_id: Mapped[str] = mapped_column(String, ForeignKey("companies.id"))
    source_url: Mapped[str] = mapped_column(String, unique=True, index=True)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    extracted_requirements: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    embedding: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now
    )

    company: Mapped["Company"] = relationship(back_populates="jobs")


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    file_path: Mapped[str] = mapped_column(String)
    embedding: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now
    )


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    job_id: Mapped[str] = mapped_column(String, ForeignKey("jobs.id"))
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus), default=ApplicationStatus.Drafted
    )
    ai_match_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cover_letter_file_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    similarity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now
    )


class InterviewPrep(Base):
    __tablename__ = "interview_prep"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    job_id: Mapped[str] = mapped_column(String, ForeignKey("jobs.id"))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_now
    )
