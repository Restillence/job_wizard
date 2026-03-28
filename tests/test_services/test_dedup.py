from src.services.job_sources.dedup import (
    normalize_text,
    normalize_company_name,
    normalize_city,
    compute_dedup_hash,
    merge_job_data,
)


class TestNormalizeText:
    def test_lowercase(self):
        assert normalize_text("Python Developer") == "python developer"

    def test_strip_whitespace(self):
        assert normalize_text("  Python  Developer  ") == "python developer"

    def test_remove_gender_suffix_mwd(self):
        assert normalize_text("Entwickler (m/w/d)") == "entwickler"

    def test_remove_gender_suffix_mfd(self):
        assert normalize_text("Developer (m/f/d)") == "developer"

    def test_remove_gender_suffix_mw(self):
        assert normalize_text("Manager (m/w)") == "manager"

    def test_remove_gender_suffix_gn(self):
        assert normalize_text("Engineer (gn)") == "engineer"

    def test_remove_special_chars(self):
        assert normalize_text("Python/Django-Dev") == "python django dev"

    def test_remove_dots_commas(self):
        assert normalize_text("Sr. Dev, Berlin") == "sr dev berlin"

    def test_collapse_whitespace(self):
        assert normalize_text("Python   Developer") == "python developer"

    def test_empty_string(self):
        assert normalize_text("") == ""

    def test_complex_title(self):
        result = normalize_text("Senior Python-Entwickler (m/w/d), Berlin")
        assert "senior" in result
        assert "python" in result
        assert "entwickler" in result
        assert "m/w/d" not in result


class TestNormalizeCompanyName:
    def test_remove_gmbh(self):
        assert normalize_company_name("SAP GmbH") == "sap"

    def test_remove_ag(self):
        assert normalize_company_name("Siemens AG") == "siemens"

    def test_remove_se(self):
        assert normalize_company_name("SAP SE") == "sap"

    def test_remove_inc(self):
        assert normalize_company_name("Google Inc") == "google"

    def test_remove_ltd(self):
        assert normalize_company_name("DeepMind Ltd") == "deepmind"

    def test_remove_llc(self):
        assert normalize_company_name("Stripe LLC") == "stripe"

    def test_remove_eg(self):
        result = normalize_company_name("Raiffeisen EG")
        assert "raiffein" in result

    def test_remove_gmbh_co_kg(self):
        assert normalize_company_name("Henkel GmbH & Co KG") == "henkel"

    def test_remove_gmbh_co_kgaa(self):
        assert normalize_company_name("Bayer GmbH & Co KGaA") == "bayer"

    def test_case_insensitive(self):
        assert normalize_company_name("sap gmbh") == "sap"

    def test_just_legal_form(self):
        result = normalize_company_name("GmbH")
        assert result.strip() == ""


class TestNormalizeCity:
    def test_muenchen(self):
        assert normalize_city("München") == "muenchen"

    def test_koeln(self):
        assert normalize_city("Köln") == "koeln"

    def test_zuerich(self):
        assert normalize_city("Zürich") == "zuerich"

    def test_nuernberg(self):
        assert normalize_city("Nürnberg") == "nuernberg"

    def test_duesseldorf(self):
        assert normalize_city("Düsseldorf") == "duesseldorf"

    def test_frankfurt_am_main(self):
        assert normalize_city("Frankfurt am Main") == "frankfurt"

    def test_regular_city(self):
        assert normalize_city("Berlin") == "berlin"

    def test_empty(self):
        assert normalize_city("") == ""


class TestComputeDedupHash:
    def test_deterministic(self):
        h1 = compute_dedup_hash("Dev", "Corp", "Berlin")
        h2 = compute_dedup_hash("Dev", "Corp", "Berlin")
        assert h1 == h2

    def test_different_title(self):
        h1 = compute_dedup_hash("Dev", "Corp", "Berlin")
        h2 = compute_dedup_hash("Manager", "Corp", "Berlin")
        assert h1 != h2

    def test_different_company(self):
        h1 = compute_dedup_hash("Dev", "Corp A", "Berlin")
        h2 = compute_dedup_hash("Dev", "Corp B", "Berlin")
        assert h1 != h2

    def test_different_city(self):
        h1 = compute_dedup_hash("Dev", "Corp", "Berlin")
        h2 = compute_dedup_hash("Dev", "Corp", "Munich")
        assert h1 != h2

    def test_gender_suffix_irrelevant(self):
        h1 = compute_dedup_hash("Entwickler (m/w/d)", "Corp", "Berlin")
        h2 = compute_dedup_hash("Entwickler", "Corp", "Berlin")
        assert h1 == h2

    def test_legal_form_irrelevant(self):
        h1 = compute_dedup_hash("Dev", "SAP GmbH", "Berlin")
        h2 = compute_dedup_hash("Dev", "SAP AG", "Berlin")
        assert h1 == h2

    def test_city_normalization(self):
        h1 = compute_dedup_hash("Dev", "Corp", "München")
        h2 = compute_dedup_hash("Dev", "Corp", "Muenchen")
        assert h1 == h2

    def test_returns_hex_string(self):
        h = compute_dedup_hash("Dev", "Corp", "Berlin")
        assert isinstance(h, str)
        assert len(h) == 64


class TestMergeJobData:
    def test_append_new_source(self):
        existing = {"sources": ["arbeitnow"], "description": "desc"}
        incoming = {"description": "desc"}
        result = merge_job_data(existing, incoming, "arbeitsagentur")
        assert "arbeitnow" in result["sources"]
        assert "arbeitsagentur" in result["sources"]

    def test_no_duplicate_source(self):
        existing = {"sources": ["arbeitnow"], "description": "desc"}
        incoming = {"description": "desc"}
        result = merge_job_data(existing, incoming, "arbeitnow")
        assert result["sources"].count("arbeitnow") == 1

    def test_backfill_missing_fields(self):
        existing = {"sources": [], "description": "desc", "salary_min": None}
        incoming = {"salary_min": 50000.0}
        result = merge_job_data(existing, incoming, "source")
        assert result["salary_min"] == 50000.0

    def test_no_overwrite_existing_fields(self):
        existing = {"sources": [], "description": "desc", "salary_min": 60000.0}
        incoming = {"salary_min": 50000.0}
        result = merge_job_data(existing, incoming, "source")
        assert result["salary_min"] == 60000.0

    def test_keep_longer_description(self):
        existing = {"sources": [], "description": "short"}
        incoming = {"description": "a much longer description with more details"}
        result = merge_job_data(existing, incoming, "source")
        assert result["description"] == "a much longer description with more details"

    def test_keep_existing_if_longer(self):
        existing = {"sources": [], "description": "a much longer description"}
        incoming = {"description": "short"}
        result = merge_job_data(existing, incoming, "source")
        assert result["description"] == "a much longer description"

    def test_backfill_multiple_fields(self):
        existing = {
            "sources": [],
            "description": "desc",
            "salary_min": None,
            "salary_max": None,
            "visa_sponsorship": None,
            "tags": None,
        }
        incoming = {
            "salary_min": 50000.0,
            "salary_max": 70000.0,
            "visa_sponsorship": True,
            "tags": ["python", "remote"],
        }
        result = merge_job_data(existing, incoming, "source")
        assert result["salary_min"] == 50000.0
        assert result["salary_max"] == 70000.0
        assert result["visa_sponsorship"] is True
        assert result["tags"] == ["python", "remote"]
