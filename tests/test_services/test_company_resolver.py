from tests.conftest import TestingSessionLocal
from src.services.job_sources.company_resolver import resolve_or_create_company
from src.services.job_sources.base import NormalizedJob
from src.models import Company


def _make_job(**overrides):
    defaults = {
        "title": "Python Developer",
        "company_name": "TestCorp",
        "source_url": "https://example.com/job/1",
        "source": "test_source",
    }
    defaults.update(overrides)
    return NormalizedJob(**defaults)


class TestResolveOrCreateCompany:
    def test_creates_new_company(self):
        db = TestingSessionLocal()
        job = _make_job(company_name="Brand New Corp")
        company, is_new = resolve_or_create_company(db, job)

        assert is_new is True
        assert company.name == "Brand New Corp"
        assert company.url_verified is False
        assert "brand-new-corp" in company.url
        db.close()

    def test_returns_existing_by_name(self):
        db = TestingSessionLocal()
        existing = Company(
            name="Existing Corp",
            url="https://existing-corp.example.com",
            url_verified=True,
        )
        db.add(existing)
        db.commit()

        job = _make_job(company_name="Existing Corp")
        company, is_new = resolve_or_create_company(db, job)

        assert is_new is False
        assert company.id == existing.id
        db.close()

    def test_returns_existing_by_url(self):
        db = TestingSessionLocal()
        unique_name = "URL Existing Corp"
        existing = Company(
            name=unique_name,
            url="https://url-existing-corp.example.com",
            url_verified=True,
        )
        db.add(existing)
        db.commit()

        job = _make_job(company_name=unique_name)
        company, is_new = resolve_or_create_company(db, job)

        assert is_new is False
        assert company.id == existing.id
        db.close()

    def test_creates_different_company(self):
        db = TestingSessionLocal()
        unique_name_a = "Corp A Unique"
        unique_name_b = "Corp B Unique"
        existing = Company(
            name=unique_name_a,
            url="https://corp-a-unique.example.com",
            url_verified=True,
        )
        db.add(existing)
        db.commit()

        job2 = _make_job(company_name=unique_name_b)
        company2, is_new2 = resolve_or_create_company(db, job2)

        assert is_new2 is True
        assert company2.name == unique_name_b
        db.close()

    def test_unknown_company_name_fallback(self):
        db = TestingSessionLocal()
        job = _make_job(company_name="  ")
        company, is_new = resolve_or_create_company(db, job)

        assert is_new is True
        assert company.name == "Unknown Company"
        db.close()

    def test_company_gets_city(self):
        db = TestingSessionLocal()
        job = _make_job(
            company_name="City Test Corp",
            location_city="Munich",
        )
        company, _ = resolve_or_create_company(db, job)

        assert company.city == "Munich"
        db.close()

    def test_no_city(self):
        db = TestingSessionLocal()
        job = _make_job(
            company_name="No City Corp",
            location_city=None,
        )
        company, _ = resolve_or_create_company(db, job)

        assert company.city is None
        db.close()
