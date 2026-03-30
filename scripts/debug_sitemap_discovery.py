"""
CRITICAL SETUP INSTRUCTIONS:
Before running this script, you MUST install the required parsing libraries.
Run this command in your active conda environment terminal:

pip install httpx beautifulsoup4 lxml

After installation, run the script:
python test_sitemap_discovery.py
"""

import asyncio
import httpx
from bs4 import BeautifulSoup

TARGET_URLS = [
    "https://jobs.kfw.de/sitemap.xml",
    "https://jobs.siemens.com/sitemap.xml",
    "https://www.bmwgroup.jobs/sitemap.xml",
    "https://matrix42.jobs.personio.com/xml",
    "https://boards.greenhouse.io/boulevard/sitemap.xml",
    "https://stout.wd5.myworkdayjobs.com/Stout-Careers-URL/sitemap.xml",
    "https://jobs.lever.co/teramind/sitemap.xml"
]

async def fetch_and_parse_sitemap(client: httpx.AsyncClient, url: str) -> tuple[int, bool, list, str]:
    """
    Fetches the sitemap and parses it robustly.
    Returns: (status_code, used_index, links, error_message)
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        response = await client.get(url, headers=headers, follow_redirects=True, timeout=30)
        status_code = response.status_code
        
        if status_code != 200:
            return status_code, False, [], f"Failed to download XML: HTTP {status_code}"

        # Use beautifulsoup with lxml-xml to be forgiving on malformed XML
        soup = BeautifulSoup(response.content, "xml")
        
        used_index = False
        
        # 1. Check for Sitemap Index (Table of Contents)
        if soup.find('sitemapindex'):
            used_index = True
            # Find the first child sitemap <loc>
            first_sitemap_loc = soup.find('loc')
            if first_sitemap_loc and first_sitemap_loc.text:
                child_url = first_sitemap_loc.text.strip()
                print(f"    -> Sitemap Index detected! Following first child: {child_url}")
                # Fetch the child sitemap
                child_response = await client.get(child_url, headers=headers, follow_redirects=True, timeout=30)
                if child_response.status_code != 200:
                     return child_response.status_code, used_index, [], f"Failed to fetch child sitemap: HTTP {child_response.status_code}"
                soup = BeautifulSoup(child_response.content, "xml")
            else:
                return status_code, used_index, [], "Sitemap index found, but no <loc> tag within it."

        # 2. Extract Links (Dialect Handler)
        links = []
        loc_tags = soup.find_all('loc')
        
        if loc_tags:
            for loc in loc_tags:
                if loc.text and loc.text.strip():
                    links.append(loc.text.strip())
        else:
            # Fallback for custom dialects like Personio
            # They might use <position> -> <url> or <job> etc.
            # Let's check for <url> inside <position>
            position_tags = soup.find_all('position')
            for pos in position_tags:
                # find url inside position or similar
                url_tag = pos.find('url')
                if url_tag and url_tag.text:
                    links.append(url_tag.text.strip())
            
            # If still empty, try looking just for <url> (Personio top level might just be <url> inside <item> or something)
            if not links:
                url_tags = soup.find_all('url')
                for u in url_tags:
                    # In standard sitemaps <url> wraps <loc>. If it's personio, <url> might contain the text or be wrapped.
                    # We just need to be careful not to grab empty <url> blocks.
                    # Personio uses <url> text? Actually Personio often has <url>https://...</url> or similar.
                    if u.text and u.text.strip() and u.text.strip().startswith('http'):
                        if '\n' not in u.text.strip(): # if it's not wrapping other elements
                             links.append(u.text.strip())

        # Clean up any duplicates while preserving order
        seen = set()
        unique_links = [x for x in links if not (x in seen or seen.add(x))]
        
        return status_code, used_index, unique_links, ""

    except Exception as e:
        return 0, False, [], str(e)


async def main():
    print("Starting Robust XML Sitemap Discovery Test...\n")
    
    async with httpx.AsyncClient(verify=False) as client: # verify=False just in case some ATS have weird certs in testing
        for url in TARGET_URLS:
            print(f"--- Target Company URL: {url} ---")
            
            status, used_index, links, error = await fetch_and_parse_sitemap(client, url)
            
            if status != 0:
                print(f"HTTP Status: {status}")
            
            print(f"Did it navigate a Sitemap Index?: {'Yes' if used_index else 'No'}")
            
            if error:
                print(f"Error Caught: {error}")
            
            print(f"Total Job Links Extracted: {len(links)}")
            
            if links:
                print("First 3 URLs:")
                for i, link in enumerate(links[:3], 1):
                    print(f"  {i}. {link}")
            
            print("\n")
            
    print("=" * 50)
    print("ROBUST SITEMAP BENCHMARKING COMPLETE")
    print("=" * 50)


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    asyncio.run(main())