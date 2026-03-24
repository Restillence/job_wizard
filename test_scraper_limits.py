import asyncio
import time
from crawl4ai import AsyncWebCrawler

TEST_URLS = [
    # Enterprise (Firewall/SPA test)
    {"category": "Enterprise", "name": "KfW", "url": "https://example.com/kfw-placeholder"},
    {"category": "Enterprise", "name": "Siemens", "url": "https://example.com/siemens-placeholder"},
    {"category": "Enterprise", "name": "BMW", "url": "https://example.com/bmw-placeholder"},
    
    # Aggregators (Anti-Bot test)
    {"category": "Aggregators", "name": "LinkedIn Jobs", "url": "https://example.com/linkedin-placeholder"},
    {"category": "Aggregators", "name": "Stepstone", "url": "https://example.com/stepstone-placeholder"},
    {"category": "Aggregators", "name": "Indeed", "url": "https://example.com/indeed-placeholder"},
    
    # Modern ATS (Baseline test)
    {"category": "Modern ATS", "name": "Personio", "url": "https://example.com/personio-placeholder"},
    {"category": "Modern ATS", "name": "Greenhouse", "url": "https://example.com/greenhouse-placeholder"},
    {"category": "Modern ATS", "name": "Workday", "url": "https://example.com/workday-placeholder"},
    {"category": "Modern ATS", "name": "Lever", "url": "https://example.com/lever-placeholder"}
]

async def main():
    print("Starting Crawler Benchmarking...\n")
    
    successful_scrapes = 0
    total_urls = len(TEST_URLS)
    
    async with AsyncWebCrawler() as crawler:
        for item in TEST_URLS:
            category = item["category"]
            name = item["name"]
            url = item["url"]
            
            print(f"--- [{category}] {name} ---")
            print(f"URL: {url}")
            
            start_time = time.time()
            try:
                result = await crawler.arun(url=url)
                latency = time.time() - start_time
                
                # Check if result is successful or contains markdown
                if getattr(result, "success", False) or (hasattr(result, "markdown") and result.markdown):
                    markdown_content = result.markdown if result.markdown else ""
                    markdown_len = len(markdown_content)
                    snippet = markdown_content[:250].replace('\n', ' ')
                    
                    print(f"Status: SUCCESS")
                    print(f"Latency: {latency:.2f} seconds")
                    print(f"Extracted Length: {markdown_len} characters")
                    print(f"Snippet: {snippet}")
                    successful_scrapes += 1
                else:
                    error_msg = getattr(result, "error_message", "No markdown returned")
                    print(f"Status: FAILED")
                    print(f"Latency: {latency:.2f} seconds")
                    print(f"Extracted Length: 0 characters")
                    print(f"Snippet: N/A - Error: {error_msg}")
                
            except Exception as e:
                latency = time.time() - start_time
                print(f"Status: FAILED")
                print(f"Latency: {latency:.2f} seconds")
                print(f"Extracted Length: 0 characters")
                print(f"Snippet: N/A - Exception: {e}")
                
            print("\n")

    print("=" * 40)
    print("BENCHMARKING COMPLETE")
    print(f"Successfully scraped {successful_scrapes}/{total_urls} URLs.")
    print("=" * 40)

if __name__ == "__main__":
    asyncio.run(main())