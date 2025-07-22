import json
import time
import logging
from urllib.parse import urljoin, urlparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import concurrent.futures
import threading

class FastWebCrawler:
    def __init__(self, base_url, max_depth=2, max_pages=20, delay=0.1):
        self.base_url = base_url
        self.domain = urlparse(base_url).netloc
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.delay = delay
        self.visited_urls = set()
        self.crawled_data = []
        self.url_queue = [(base_url, 0)]
        self.lock = threading.Lock()
        
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
    def create_driver(self):
        """Create optimized Chrome driver"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-images")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--aggressive-cache-discard")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        
        # Block unnecessary resources
        prefs = {
            "profile.managed_default_content_settings.images": 2,
            "profile.managed_default_content_settings.stylesheets": 2,
            "profile.managed_default_content_settings.cookies": 2,
            "profile.managed_default_content_settings.javascript": 1,
            "profile.managed_default_content_settings.plugins": 2,
            "profile.managed_default_content_settings.popups": 2,
            "profile.managed_default_content_settings.geolocation": 2,
            "profile.managed_default_content_settings.media_stream": 2,
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except:
            driver = webdriver.Chrome(options=chrome_options)
            
        driver.implicitly_wait(1)
        driver.set_page_load_timeout(15)
        return driver
        
    def extract_essential_data(self, driver, url, depth):
        """Extract only essential data quickly"""
        try:
            driver.get(url)
            time.sleep(self.delay)
            
            # Get page source
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # Extract links quickly
            links = []
            for link in soup.find_all('a', href=True):
                href = link['href']
                if href:
                    absolute_url = urljoin(url, href)
                    if self.is_valid_url(absolute_url):
                        links.append(absolute_url)
            
            # Extract basic page info
            page_data = {
                'url': url,
                'title': driver.title or soup.title.string if soup.title else '',
                'depth': depth,
                'links_found': len(links),
                'links': links[:10],  # Limit to first 10 links
                'has_pagination': self.quick_pagination_check(soup),
                'has_dynamic_content': self.quick_dynamic_check(soup),
                'headings': {
                    'h1': [h.get_text().strip() for h in soup.find_all('h1')[:3]],
                    'h2': [h.get_text().strip() for h in soup.find_all('h2')[:3]]
                }
            }
            
            return page_data, links
            
        except Exception as e:
            self.logger.error(f"Error crawling {url}: {e}")
            return None, []
            
    def quick_pagination_check(self, soup):
        """Quick check for pagination elements"""
        pagination_indicators = ['next', 'prev', 'page', 'pagination']
        for indicator in pagination_indicators:
            if soup.find(attrs={'class': lambda x: x and indicator in x.lower()}):
                return True
            if soup.find(string=lambda text: text and indicator in text.lower()):
                return True
        return False
        
    def quick_dynamic_check(self, soup):
        """Quick check for dynamic content"""
        dynamic_indicators = ['load-more', 'show-more', 'carousel', 'slider', 'tab']
        for indicator in dynamic_indicators:
            if soup.find(attrs={'class': lambda x: x and indicator in x.lower()}):
                return True
        return len(soup.find_all('ul')) > 3  # Many lists might indicate dynamic content
        
    def is_valid_url(self, url):
        """Check if URL is valid and from same domain"""
        try:
            parsed = urlparse(url)
            return (parsed.netloc == self.domain or parsed.netloc == "") and \
                   not any(ext in url.lower() for ext in ['.pdf', '.jpg', '.png', '.gif', '.zip'])
        except:
            return False
            
    def crawl_single_page(self, url, depth):
        """Crawl a single page with its own driver"""
        if len(self.crawled_data) >= self.max_pages:
            return []
            
        driver = self.create_driver()
        try:
            page_data, new_links = self.extract_essential_data(driver, url, depth)
            if page_data:
                with self.lock:
                    if len(self.crawled_data) < self.max_pages:
                        self.crawled_data.append(page_data)
                        self.logger.info(f"Crawled: {url} (depth: {depth}) - Page {len(self.crawled_data)}/{self.max_pages}")
                return new_links if depth < self.max_depth else []
        finally:
            driver.quit()
        return []
        
    def crawl(self):
        """Main crawling method with optimized processing"""
        start_time = time.time()
        
        while self.url_queue and len(self.crawled_data) < self.max_pages:
            current_batch = []
            
            # Process URLs in batches
            for _ in range(min(3, len(self.url_queue))):  # Process 3 URLs at once
                if self.url_queue:
                    url, depth = self.url_queue.pop(0)
                    if url not in self.visited_urls:
                        self.visited_urls.add(url)
                        current_batch.append((url, depth))
            
            if not current_batch:
                break
                
            # Process batch concurrently
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                future_to_url = {
                    executor.submit(self.crawl_single_page, url, depth): url 
                    for url, depth in current_batch
                }
                
                for future in concurrent.futures.as_completed(future_to_url):
                    new_links = future.result()
                    
                    # Add new links to queue
                    for link in new_links:
                        if link not in self.visited_urls and len(self.url_queue) < 100:
                            self.url_queue.append((link, current_batch[0][1] + 1))
        
        end_time = time.time()
        self.logger.info(f"Crawling completed in {end_time - start_time:.2f} seconds")
        return self.crawled_data
        
    def save_to_json(self, filename='fast_crawled_data.json'):
        """Save crawled data to JSON file"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.crawled_data, f, indent=2, ensure_ascii=False)
        self.logger.info(f"Data saved to {filename}")
        
    def get_summary(self):
        """Get crawling summary"""
        total_pages = len(self.crawled_data)
        total_links = sum(page['links_found'] for page in self.crawled_data)
        pages_with_pagination = sum(1 for page in self.crawled_data if page['has_pagination'])
        pages_with_dynamic = sum(1 for page in self.crawled_data if page['has_dynamic_content'])
        
        return {
            'total_pages_crawled': total_pages,
            'total_links_found': total_links,
            'pages_with_pagination': pages_with_pagination,
            'pages_with_dynamic_content': pages_with_dynamic,
            'crawl_depth_reached': max(page['depth'] for page in self.crawled_data) if self.crawled_data else 0,
            'unique_urls_visited': len(self.visited_urls)
        }

if __name__ == "__main__":
    base_url = input("Enter the base URL to crawl: ").strip()
    max_pages = int(input("Enter max pages to crawl (default 20): ") or 20)
    max_depth = int(input("Enter max depth (default 2): ") or 2)
    
    crawler = FastWebCrawler(base_url, max_depth=max_depth, max_pages=max_pages)
    
    print("Starting fast crawl...")
    crawled_data = crawler.crawl()
    
    # Save results
    crawler.save_to_json()
    
    # Print summary
    summary = crawler.get_summary()
    print("\nCrawl Summary:")
    print(json.dumps(summary, indent=2))