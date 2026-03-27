import requests
from bs4 import BeautifulSoup
import json
import re
import logging
from typing import List, Dict, Any
from urllib.parse import urljoin
from litellm import completion
from src.config import settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class UniversalCareerScraper:
    def __init__(self, url: str):
        self.url = url
        self.html = ""
        self.soup = None
        self.jobs = []
        
    def fetch_page(self):
        """Fetches the target URL with basic anti-blocking headers."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            response = requests.get(self.url, headers=headers, timeout=15)
            response.raise_for_status()
            self.html = response.text
            self.soup = BeautifulSoup(self.html, 'html.parser')
            
            # Monitoring Mechanism: Check if HTML is substantially large
            # Many WAFs/Captchas return small HTML stubs.
            if len(self.html) < 1000:
                logging.warning("HTML content is suspiciously small. Possible CAPTCHA or blocking.")
                
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching {self.url}: {e}")
            raise
            
    def tier_1_json_ld(self) -> bool:
        """Layer 1: Extract JSON-LD JobPosting metadata from the HTML."""
        logging.info("Attempting Tier 1: JSON-LD Extraction")
        if not self.soup:
            return False
            
        scripts = self.soup.find_all('script', type='application/ld+json')
        for script in scripts:
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
                # JSON-LD can be a single dict or a list of dicts
                if isinstance(data, dict):
                    # Sometimes it's wrapped in a graph
                    if '@graph' in data:
                        data = data['@graph']
                    else:
                        data = [data]
                
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get('@type') == 'JobPosting':
                            job = {
                                "title": item.get('title', 'Unknown Title'),
                                "url": item.get('url', self.url),
                                "location": self._extract_json_ld_location(item),
                                "source": "Tier 1: JSON-LD"
                            }
                            self.jobs.append(job)
            except json.JSONDecodeError:
                continue
                
        if self.jobs:
            logging.info(f"Tier 1 successful: Found {len(self.jobs)} jobs via JSON-LD.")
            return True
        return False

    def _extract_json_ld_location(self, item: dict) -> str:
        """Helper to safely extract location from JSON-LD."""
        loc = item.get('jobLocation', {})
        if isinstance(loc, list) and len(loc) > 0:
            loc = loc[0]
        if isinstance(loc, dict):
            address = loc.get('address', {})
            if isinstance(address, dict):
                return address.get('addressLocality', 'Unknown Location')
        return 'Unknown Location'

    def tier_2_ats_detection(self) -> bool:
        """Layer 2: Detect common ATS platforms and parse their data formats."""
        logging.info("Attempting Tier 2: ATS Detection")
        html_lower = self.html.lower()
        
        # Greenhouse
        if 'greenhouse.io' in html_lower or 'greenhouse' in self.url.lower():
            logging.info("Detected ATS: Greenhouse")
            links = self.soup.find_all('a', href=re.compile(r'greenhouse\.io.*/jobs/\d+'))
            # Sometimes they use relative links on a Greenhouse hosted board
            if not links and 'greenhouse.io' in self.url:
                 links = self.soup.find_all('a', href=re.compile(r'/jobs/\d+'))
                 
            for link in links:
                href = urljoin(self.url, link.get('href'))
                self.jobs.append({"title": link.text.strip(), "url": href, "source": "Tier 2: ATS-Greenhouse"})
            if self.jobs: return True
            
        # Lever
        elif 'jobs.lever.co' in html_lower or 'lever' in self.url.lower():
            logging.info("Detected ATS: Lever")
            links = self.soup.find_all('a', href=re.compile(r'jobs\.lever\.co.*/[a-zA-Z0-9-]+'))
            for link in links:
                href = urljoin(self.url, link.get('href'))
                self.jobs.append({"title": link.text.strip(), "url": href, "source": "Tier 2: ATS-Lever"})
            if self.jobs: return True
            
        # Personio
        elif 'personio.de' in html_lower or 'personio.com' in html_lower or 'personio' in self.url.lower():
            logging.info("Detected ATS: Personio")
            # Personio typically uses /job/12345
            links = self.soup.find_all('a', href=re.compile(r'/job/\d+'))
            for link in links:
                href = urljoin(self.url, link.get('href'))
                title_elem = link.text.strip()
                if not title_elem:
                    # sometimes the text is nested
                    title_elem = "Personio Job"
                self.jobs.append({"title": title_elem, "url": href, "source": "Tier 2: ATS-Personio"})
            if self.jobs: return True
            
        return False

    def tier_3_heuristic(self) -> bool:
        """Layer 3: Use a heuristic crawler with BeautifulSoup to find typical job links."""
        logging.info("Attempting Tier 3: Heuristic Link Extraction")
        keywords = ['/jobs/', '/job/', '/career/', '/stellenangebote/', '/position/', '/vacancy/', '/role/']
        
        links = self.soup.find_all('a', href=True)
        for link in links:
            href = link['href'].lower()
            
            # Skip generic links
            if any(ex in href for ex in ['/login', '/about', '/privacy', 'mailto:']):
                continue
                
            if any(kw in href for kw in keywords):
                absolute_url = urljoin(self.url, link['href'])
                title = link.text.strip()
                if not title:
                    # Try to find a header inside the link
                    nested_header = link.find(['h2', 'h3', 'h4', 'span'])
                    if nested_header:
                        title = nested_header.text.strip()
                        
                if title:
                    self.jobs.append({
                        "title": title,
                        "url": absolute_url,
                        "source": "Tier 3: Heuristic"
                    })
                
        if self.jobs:
             # Deduplicate based on URL
             unique_jobs = {j['url']: j for j in self.jobs}.values()
             self.jobs = list(unique_jobs)
             logging.info(f"Tier 3 successful: Found {len(self.jobs)} jobs heuristically.")
             return True
             
        return False

    def tier_4_llm_fallback(self) -> bool:
        """Layer 4: LLM extraction using cleaned HTML text."""
        logging.info("Attempting Tier 4: LLM Fallback")
        
        # 1. Clean the HTML for the LLM context window
        for element in self.soup(["script", "style", "nav", "footer", "header", "noscript"]):
            element.extract()
            
        # 2. Extract visible text
        text = self.soup.get_text(separator=' ', strip=True)
        # Collapse multiple spaces
        clean_text = re.sub(r'\s+', ' ', text)
        
        # Limit text to avoid blowing up the context window
        if len(clean_text) > 25000:
            clean_text = clean_text[:25000]
            
        logging.info(f"Prepared {len(clean_text)} characters of clean text for LLM.")
        
        prompt = f"""
        Extract job titles and their application URLs from the following cleaned webpage text.
        Also extract the location if available.
        
        Text Content:
        {clean_text}
        
        Return ONLY a valid JSON object matching this schema:
        {{
          "jobs": [
            {{"title": "Software Engineer", "url": "https://...", "location": "Munich"}}
          ]
        }}
        Do not include markdown formatting like ```json.
        """
        
        import os
        os.environ['ZAI_API_KEY'] = settings.ZAI_API_KEY
        
        try:
            logging.info("Calling LLM with model: zai/glm-5")
            response = completion(
                model="zai/glm-5",
                messages=[{"role": "user", "content": prompt}],
            )
            raw_json = response.choices[0].message.content.strip()
            
            if raw_json.startswith("```"):
                raw_json = re.sub(r"^```(?:json)?\n|\n```$", "", raw_json)
                
            parsed_data = json.loads(raw_json)
            extracted_jobs = parsed_data.get("jobs", [])
            
            for job in extracted_jobs:
                title = job.get("title")
                url = job.get("url")
                location = job.get("location", "Unknown Location")
                
                if title and url:
                    if "about" in url.lower() or "privacy" in url.lower():
                        continue
                    absolute_url = urljoin(self.url, url)
                    self.jobs.append({
                        "title": title,
                        "url": absolute_url,
                        "location": location,
                        "source": "Tier 4: LLM Extraction"
                    })
                    
            if self.jobs:
                # Deduplicate based on URL
                unique_jobs = {j['url']: j for j in self.jobs}.values()
                self.jobs = list(unique_jobs)
                logging.info(f"Tier 4 successful: Found {len(self.jobs)} jobs via LLM.")
                return True
                
        except Exception as e:
            logging.error(f"LLM fallback extraction failed: {e}")
            
        return False

    def verify_and_alert(self):
        """Monitoring mechanism to verify results are up-to-date and valid."""
        logging.info("Running strict verification and monitoring...")
        if not self.jobs:
            # Throw an alert if zero jobs are found
            error_msg = f"ALERT: Zero jobs found on {self.url}! The structure might be broken, stale, or heavily firewalled."
            logging.error(error_msg)
            raise ValueError(error_msg)
            
        logging.info(f"Verification Passed! Pipeline successfully extracted {len(self.jobs)} jobs.")

    def run(self) -> List[Dict[str, Any]]:
        """Executes the 4-tier fallback architecture."""
        logging.info(f"Starting Universal Scraper for: {self.url}")
        try:
            self.fetch_page()
            
            # Execute tiers sequentially, stopping when jobs are found
            if self.tier_1_json_ld():
                pass
            elif self.tier_2_ats_detection():
                pass
            elif self.tier_3_heuristic():
                pass
            else:
                self.tier_4_llm_fallback()
                
            # Verify the final state
            self.verify_and_alert()
            return self.jobs
            
        except Exception as e:
            logging.error(f"Scraping pipeline failed for {self.url} with error: {e}")
            return []

if __name__ == "__main__":
    # Test cases to demonstrate the scraper
    test_urls = [
        "https://jobs.kfw.de/",                          # Added KfW
        "https://jobs.siemens.com/careers",              # Likely Tier 3 Heuristics
        "https://adragos-pharma.jobs.personio.de",       # ATS Personio (Tier 2)
        "https://example.com/broken-page-test"           # Will trigger the zero-jobs alert
    ]
    
    for test_url in test_urls:
        print("\n" + "="*80)
        scraper = UniversalCareerScraper(test_url)
        results = scraper.run()
        if results:
            print(f"\n[SUCCESS] Top 3 Extracted Jobs for {test_url}:")
            for i, job in enumerate(results[:3], 1):
                print(f"  {i}. {job['title']} -> {job['url']} ({job['source']})")
        else:
            print(f"\n[FAILED] Could not extract jobs from {test_url}")
