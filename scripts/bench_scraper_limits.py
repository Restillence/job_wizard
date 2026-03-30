import asyncio
import time
from crawl4ai import AsyncWebCrawler

TEST_URLS = [
    # Enterprise (Firewall/SPA test)
    {"category": "Enterprise", "name": "KfW", "url": "https://jobs.kfw.de/index.php?ac=jobad&id=12933"},
    {"category": "Enterprise", "name": "Siemens", "url": "https://jobs.siemens.com/de_DE/externaljobs/JobDetail/499958"},
    {"category": "Enterprise", "name": "BMW", "url": "https://www.bmwgroup.jobs/de/de/jobfinder/job-description.182761.html"},
    
    # Aggregators (Anti-Bot test)
    {"category": "Aggregators", "name": "LinkedIn Jobs", "url": "https://www.linkedin.com/jobs/collections/recommended/?trackingId=6Wj%2B%2B%2Ff9I0gOd3GTinFCIg%3D%3D&currentJobId=4312704611&refId=vmh5GGtw4wUPobf9Yhtnhg%3D%3D&eBP=CwEAAAGdH-yq4bJ86y_NdVniKojdw32Rd93iSdX4hJdx43Y56Dl-XaR5nlJJPwBw0WYGYJBH6pHwhRjqWH5UzWJ-y_-LJjANCm-8YsZLclri9uU4U1jveH7iFh2R9uUsf35R28EiFAAk8AMz5ZE-2-9wg853AmESkY2n6k2ciTplE2kuAQZ2G1lBThg6Hbe-kGkPZdPBT2X-FLVniRt8hbsWv7utPEKOwy-17sFucMQtAOxEIw6I7Yi-0VVukqhvzTMPqCl9_cslyoyIdFk_lqfTCsGhxqXPlbcNaNdTjDR3_QnuW5C9Wu4sQgiIwhNcSvEVwbHv0r5HiHGrmZrdmARBPQRl9V8IQz0rYz_rM3KAlK7vNkmwIEwXZk318NePNtAseOU-iLBfg8c5t33KNe69iwaX-APtsLHSefHkL3sGt3ESZ-RhYtTHizJ-vMp-P4Qnro242fz530e3luzjcEWQVV8Ukmy07ODtfHLKh_GqLTHqg-Z7BFlG3n13aw&lipi=urn%3Ali%3Apage%3Ad_flagship3_job_home%3Bo22gfN9iSuGHU%2FdOmZx1MA%3D%3D"},
    {"category": "Aggregators", "name": "Stepstone", "url": "https://www.stepstone.de/stellenangebote--Associate-Consultant-Data-Innovation-I-Data-Driven-Government-m-w-d-Berlin-Frankfurt-am-Main-Hamburg-Koeln-Muenchen-Stuttgart-Capgemini-Invent--9933897-inline.html?rltr=16_16_25_seorl_m_0_1_3_0_0_0"},
    {"category": "Aggregators", "name": "Indeed", "url": "https://de.indeed.com/viewjob?jk=4973d2471bf786cc&from=shareddesktop_copy"},
    
    # Modern ATS (Baseline test)
{
        "category": "Modern ATS",
        "name": "Personio",
        "url": "https://matrix42.jobs.personio.com/job/2493797?language=en"
    },
    {
        "category": "Modern ATS",
        "name": "Greenhouse",
        "url": "https://job-boards.greenhouse.io/boulevard/jobs/4652156006"
    },
    {
        "category": "Modern ATS",
        "name": "Workday",
        "url": "https://stout.wd5.myworkdayjobs.com/Stout-Careers-URL/job/Chicago-IL/Manager--Forensics-and-Compliance---Disputes--Claims---Investigations_r1947"
    },
    {
        "category": "Modern ATS",
        "name": "Lever",
        "url": "https://jobs.lever.co/teramind/fdbc0a8d-b618-49ef-a8a6-f138340f583c"
    }
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