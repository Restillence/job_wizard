import asyncio
import re
import time
from typing import List, Dict, Any
from urllib.parse import urljoin
from crawl4ai import AsyncWebCrawler

# List of 5 Root Career URLs to test as a Spider
TEST_URLS = [
    "https://jobs.kfw.de",
    "https://jobs.siemens.com/careers",
    "https://adragos-pharma.jobs.personio.de",
    "https://careers.bmwgroup.com",
    "https://careers.roche.com/global/en/search-results"
]

def is_job_link(href: str) -> bool:
    """
    Filter logic to determine if a link likely points to a job posting.
    """
    if not href:
        return False
        
    url_lower = href.lower()
    
    # Generic exclusions
    exclusions = [
        '/about', '/privacy', '/terms', '/imprint', '/impressum', 
        '/contact', '/login', '/cookie', 'mailto:', 'javascript:', '#'
    ]
    if any(ex in url_lower for ex in exclusions) or url_lower == '/':
        return False
        
    # Typical job URL indicators
    inclusions = [
        '/job', '/position', '/career', '/stellen', '/vacancy', '/role', '/posting'
    ]
    if any(inc in url_lower for inc in inclusions):
        return True
        
    # Check for long ID numbers or alphanumeric hashes which often represent jobs
    # e.g., /12345/ or ?id=98765
    if re.search(r'/\d{5,}(?:/|\?|$)', url_lower) or re.search(r'id=\d{4,}', url_lower):
        return True
        
    return False

def extract_all_links(result: Any, base_url: str) -> List[str]:
    """
    Safely extract all links from the crawl4ai result.
    Crawl4ai typically stores links in result.links as a dict of 'internal' and 'external'.
    """
    all_links = set()
    
    if hasattr(result, 'links') and isinstance(result.links, dict):
        for category in ['internal', 'external']:
            for link_obj in result.links.get(category, []):
                href = link_obj.get('href', '')
                if href:
                    # Make relative URLs absolute
                    absolute_url = urljoin(base_url, href)
                    all_links.add(absolute_url)
                    
    return list(all_links)

async def main():
    print("Starting Spider Benchmarking...\n")
    
    async with AsyncWebCrawler() as crawler:
        for url in TEST_URLS:
            print(f"--- Target URL: {url} ---")
            
            start_time = time.time()
            try:
                # Using bypass_cache=True to ensure we hit the live page
                result = await crawler.arun(url=url, bypass_cache=True)
                latency = time.time() - start_time
                
                if getattr(result, "success", False):
                    status = "Success"
                    
                    # Extract raw links
                    raw_links = extract_all_links(result, url)
                    total_raw_links = len(raw_links)
                    
                    # Filter for job links
                    job_links = [link for link in raw_links if is_job_link(link)]
                    total_job_links = len(job_links)
                    
                    print(f"Status: {status} ({latency:.2f}s)")
                    print(f"Total raw links found: {total_raw_links}")
                    print(f"Total filtered job links found: {total_job_links}")
                    
                    if total_job_links > 0:
                        print("First 3 job links found:")
                        for i, jl in enumerate(job_links[:3], 1):
                            print(f"  {i}. {jl}")
                    else:
                        print("No job links found.")
                else:
                    error_msg = getattr(result, "error_message", "Unknown Error")
                    print(f"Status: Failed ({latency:.2f}s) - {error_msg}")
                    print(f"Total raw links found: 0")
                    print(f"Total filtered job links found: 0")
                    
            except Exception as e:
                latency = time.time() - start_time
                print(f"Status: Timeout/Error ({latency:.2f}s) - Exception: {str(e)}")
                print(f"Total raw links found: 0")
                print(f"Total filtered job links found: 0")
                
            print("\n")

    print("=" * 40)
    print("SPIDER BENCHMARKING COMPLETE")
    print("=" * 40)

if __name__ == "__main__":
    asyncio.run(main())