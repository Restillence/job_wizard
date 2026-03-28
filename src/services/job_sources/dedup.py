import hashlib
import re


_LEGAL_FORMS = [
    "gmbh & co kg",
    "gmbh & co kgaa",
    "stiftung & co kg",
    "gmbh",
    "ag",
    "se",
    "kg",
    "inc",
    "ltd",
    "llc",
    "eg",
]

_CITY_NORMALIZATIONS = {
    "münchen": "muenchen",
    "köln": "koeln",
    "zürich": "zuerich",
    "nürnberg": "nuernberg",
    "düsseldorf": "duesseldorf",
    "frankfurt am main": "frankfurt",
    "wien": "wien",
}

_GENDER_SUFFIXES = [
    r"\(m/w/d\)",
    r"\(f/m/x\)",
    r"\(w/m/d\)",
    r"\(m/f/d\)",
    r"\(all\s*genders\)",
    r"\(m/w\)",
    r"\(w/m\)",
    r"\(m/f\)",
    r"\(f/m\)",
    r"\(d/m/w\)",
    r"\(d/f/m\)",
    r"\(w/d/m\)",
    r"\(m/d/w\)",
    r"\(m/w/d/l\)",
    r"\(gn\)",
    r"\(mwd\)",
    r"\(wmd\)",
    r"\(fmd\)",
]


def _remove_gender_suffixes(text: str) -> str:
    for pattern in _GENDER_SUFFIXES:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    return text


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    text = _remove_gender_suffixes(text)
    text = re.sub(r"[.,\-/]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_company_name(name: str) -> str:
    normalized = normalize_text(name)
    for form in sorted(_LEGAL_FORMS, key=len, reverse=True):
        normalized = normalized.replace(form, "")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def normalize_city(city: str) -> str:
    normalized = normalize_text(city)
    for original, replacement in _CITY_NORMALIZATIONS.items():
        if normalized == original:
            return replacement
    return normalized


def compute_dedup_hash(title: str, company_name: str, city: str) -> str:
    normalized_title = normalize_text(title)
    normalized_company = normalize_company_name(company_name)
    normalized_city = normalize_city(city)
    fingerprint = f"{normalized_title}|{normalized_company}|{normalized_city}"
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()


def merge_job_data(
    existing: dict,
    incoming: dict,
    source_name: str,
) -> dict:
    sources = existing.get("sources", [])
    if source_name not in sources:
        sources.append(source_name)

    merged = {**existing, "sources": sources}

    backfill_fields = [
        "salary_min",
        "salary_max",
        "salary_currency",
        "visa_sponsorship",
        "tags",
        "location_region",
        "location_country",
        "job_types",
        "posted_at",
        "expires_at",
    ]

    for field in backfill_fields:
        if merged.get(field) is None and incoming.get(field) is not None:
            merged[field] = incoming[field]

    if incoming.get("description") and len(incoming["description"] or "") > len(
        merged.get("description") or ""
    ):
        merged["description"] = incoming["description"]

    return merged
