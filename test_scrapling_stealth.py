# Run 'pip install scrapling' before executing.

import re
from urllib.parse import urljoin
from scrapling import StealthyFetcher

def is_job_link(href: str) -> bool:
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
        '/job', '/position', '/career', '/stellen', '/vacancy', '/role', '/posting', '?ac=jobad'
    ]
    if any(inc in url_lower for inc in inclusions):
        return True
        
    # Check for long ID numbers or alphanumeric hashes which often represent jobs
    if re.search(r'/\d{5,}(?:/|\?|$)', url_lower) or re.search(r'id=\d{4,}', url_lower):
        return True
        
    return False

def main():
    target_url = "https://jobs.kfw.de/"
    
    print("Starting Scrapling Stealth Spider Test...\n")
    print("Initializing StealthyFetcher with headless=False")
    
    try:
        fetcher = StealthyFetcher(headless=False)
        print(f"Fetching Target URL: {target_url}...")
        
        page = fetcher.fetch(target_url)
        
        status_code = getattr(page, 'status', '200 (Assumed)')
        print(f"HTTP Status Code: {status_code}")
        
        # Extract all anchor tags
        print("Extracting links...")
        # Scrapling css selector returns elements, we can get attributes via .attrib or .css('a::attr(href)')
        # Some versions prefer a::attr(href), but iterating elements is safer.
        elements = page.css('a')
        
        raw_links = set()
        for el in elements:
            # Scrapling element attributes are usually accessed via .attrib dictionary
            if hasattr(el, 'attrib') and 'href' in el.attrib:
                href = el.attrib['href']
                absolute_url = urljoin(target_url, href)
                raw_links.add(absolute_url)
                
        raw_links = list(raw_links)
        
        # Filter for job links
        job_links = [link for link in raw_links if is_job_link(link)]
        
        print(f"Total raw links found: {len(raw_links)}")
        print(f"Total filtered job links found: {len(job_links)}")
        
        if job_links:
            print("\nFirst 5 job links found:")
            for i, jl in enumerate(job_links[:5], 1):
                print(f"  {i}. {jl}")
        else:
            print("No job links found.")
            
    except Exception as e:
        print(f"Stealth spider failed with Exception: {str(e)}")

if __name__ == "__main__":
    main()
