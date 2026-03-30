"""
CRITICAL SETUP INSTRUCTIONS:
Before running this script, you MUST install Playwright and its browser binaries.
Run these two commands in your active conda environment terminal:

1. pip install playwright
2. playwright install

After installation, run the script:
python test_playwright_interceptor.py
"""

import asyncio
import json
from playwright.async_api import async_playwright

async def handle_response(response):
    url = response.url.lower()
    
    # 1. Check if URL contains API-like keywords
    keywords = ['api', 'graphql', 'search', 'jobs', 'facet']
    if not any(keyword in url for keyword in keywords):
        return
        
    # 2. Check if response headers indicate JSON content
    content_type = response.headers.get('content-type', '')
    if 'application/json' not in content_type:
        return

    # 3. Safely extract and inspect JSON
    try:
        json_data = await response.json()
        
        print("="*80)
        print(f"[INTERCEPTED API] {response.url}")
        print("="*80)
        
        # Try to find typical job data heuristics (total counts, job lists)
        if isinstance(json_data, dict):
            found_heuristics = False
            for key in ['total', 'totalCount', 'count', 'hits', 'jobs', 'results', 'requisitions', 'eagerLoadRefineSearch']:
                if key in json_data:
                    print(f"-> Found potential job metric '{key}': {type(json_data[key]).__name__} (Length/Value: {len(json_data[key]) if isinstance(json_data[key], (list, dict)) else json_data[key]})")
                    found_heuristics = True
            
            if found_heuristics:
                print("\n[Snippet of Payload]")
                # Dump a truncated version of the JSON
                snippet = json.dumps(json_data, indent=2)[:500]
                print(snippet + "\n... [TRUNCATED] ...\n")
        elif isinstance(json_data, list):
            print(f"-> Payload is a JSON Array of length {len(json_data)}")
            print("\n[Snippet of Payload]")
            snippet = json.dumps(json_data, indent=2)[:500]
            print(snippet + "\n... [TRUNCATED] ...\n")
            
    except Exception as e:
        # Ignore requests that fail to parse or were aborted
        pass

async def main():
    target_url = "https://careers.roche.com/global/en/search-results"
    
    print("Launching Chromium (headless=False) to monitor background API requests...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Set up network listener BEFORE navigating
        page.on("response", handle_response)
        
        print(f"Navigating to {target_url}...")
        try:
            await page.goto(target_url, wait_until="domcontentloaded")
            
            print("Waiting for network idle state (all background APIs finished)...")
            await page.wait_for_load_state('networkidle', timeout=20000)
            
        except Exception as e:
            print(f"Note: Network idle wait timed out or failed (common in SPAs): {e}")
            
        print("Waiting an additional 3 seconds just to be safe...")
        await asyncio.sleep(3)
        
        print("\nClosing browser...")
        await browser.close()
        print("Done.")

if __name__ == "__main__":
    asyncio.run(main())