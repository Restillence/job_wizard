import asyncio
from src.database import SessionLocal
from src.services.job_discovery import JobDiscoveryService
from src.config import settings

async def main():
    print(f"Using ZAI API for LLM Extraction: {settings.ZAI_API_BASE}")
    print("Initializing Database Session...")
    db = SessionLocal()
    
    service = JobDiscoveryService()
    
    # We use a specific query to demonstrate it
    cities = ["Munich"]
    industries = ["Robotics"]
    
    print("\n" + "="*70)
    print(f"Starting LIVE Job Discovery: Cities={cities}, Industries={industries}")
    print("="*70 + "\n")
    
    print("1. Querying Local DB & calculating threshold...")
    print("2. (If below threshold) Executing Real Web Search (DuckDuckGo/Tavily)...")
    print("3. Passing search snippets to LLM to extract real company names...")
    print("4. Asking LLM to predict their career pages...")
    print("5. Making real HEAD requests to verify URLs exist...")
    print("-" * 40 + "\n")

    # Call the actual service logic
    result = await service.search_companies(
        db=db,
        cities=cities,
        industries=industries
    )
    
    print("\n" + "="*70)
    print(f"RESULTS (Source: {result.source})")
    print("="*70)
    print(f"Total Found: {result.total_found}")
    print(f"Newly Added to DB: {result.newly_added}")
    
    print("\nCompanies:")
    for c in result.companies:
        print(f" - {c['name']} (City: {c['city']}, Industry: {c['industry']})")
        verified_status = "✅ Verified" if c['url_verified'] else "❌ Unverified"
        print(f"   URL: {c['url']} [{verified_status}]")
        print()
        
    db.close()

if __name__ == "__main__":
    asyncio.run(main())
