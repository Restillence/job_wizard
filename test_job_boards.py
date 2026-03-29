from src.services.job_sources.arbeitsagentur import ArbeitsagenturSource
from src.services.job_sources.arbeitnow import ArbeitnowSource
from src.services.job_sources.base import SearchParams


def test_arbeitsagentur():
    print("=" * 60)
    print("ARBEITSAGENTUR (DE only, no credentials needed)")
    print("=" * 60)

    src = ArbeitsagenturSource()
    params = SearchParams(query="Data Science Trainee", city="Frankfurt", per_page=20)
    jobs = src.fetch(params)

    if not jobs:
        print("  No results (API might be rate-limited, try again later)")
    for j in jobs:
        print(f"  {j.title}")
        print(f"    Company:  {j.company_name}")
        print(f"    Location: {j.location_city}, {j.location_country}")
        print(f"    URL:      {j.source_url}")
        print()


def test_arbeitnow():
    print("=" * 60)
    print("ARBEITNOW (DE/AT/CH, no credentials needed)")
    print("=" * 60)

    src = ArbeitnowSource()
    params = SearchParams(country="DE", city="Berlin", per_page=10)
    jobs = src.fetch(params)

    if not jobs:
        print("  No results (API might be rate-limited, try again later)")
    for j in jobs:
        print(f"  {j.title}")
        print(f"    Company:  {j.company_name}")
        print(f"    Location: {j.location_city}, {j.location_country}")
        print(f"    Remote:   {j.remote}")
        print(f"    URL:      {j.source_url}")
        print()


if __name__ == "__main__":
    test_arbeitsagentur()
    test_arbeitnow()
