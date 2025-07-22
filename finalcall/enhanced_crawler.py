import json
import time
import logging
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import concurrent.futures
import threading

class EnhancedWebCrawler:
    def __init__(self, base_url, max_depth=5, max_pages=200, use_selenium=True, exhaustive=True, dynamic_discovery=True):
        self.base_url = base_url
        self.domain = urlparse(base_url).netloc
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.use_selenium = use_selenium
        self.exhaustive = exhaustive
        self.dynamic_discovery = dynamic_discovery
        self.visited_urls = set()
        self.crawled_data = []
        self.url_queue = [(base_url, 0)]
        self.lock = threading.Lock()
        self.all_discovered_links = set()
        self.dynamic_urls_found = set()
        
        # Setup session for requests
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
    def create_selenium_driver(self):
        """Create optimized Selenium driver"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-logging")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # Allow JavaScript but block images for speed
        prefs = {
            "profile.managed_default_content_settings.images": 2,
            "profile.managed_default_content_settings.stylesheets": 2,
            "profile.managed_default_content_settings.javascript": 1,
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.set_page_load_timeout(15)
            driver.implicitly_wait(3)
            return driver
        except Exception as e:
            self.logger.error(f"Failed to create Selenium driver: {e}")
            return None
    
    def extract_links_from_driver(self, driver, base_url):
        """Extract all links from current driver state"""
        links = []
        try:
            link_elements = driver.find_elements(By.CSS_SELECTOR, "a[href]")
            for link in link_elements:
                href = link.get_attribute('href')
                if href:
                    absolute_url = urljoin(base_url, href)
                    if self.is_valid_url(absolute_url):
                        links.append(absolute_url)
        except Exception as e:
            self.logger.debug(f"Error extracting links: {e}")
        return links

    def handle_numbered_pagination(self, driver, url, initial_links):
        """Handle numbered pagination (1, 2, 3, 4, ..., 8) like in card layouts"""
        pagination_links = []
        
        try:
            self.logger.info(f"🔢 Looking for numbered pagination on {url}")
            
            # JavaScript to find pagination elements more reliably
            pagination_script = """
            var paginationLinks = [];
            var allElements = document.querySelectorAll('a, button, span[onclick], div[onclick]');
            
            for (var i = 0; i < allElements.length; i++) {
                var element = allElements[i];
                var text = element.textContent.trim();
                var href = element.href || '';
                var onclick = element.onclick || element.getAttribute('onclick') || '';
                
                // Look for numbered pagination (2, 3, 4, etc.) - skip 1 as it's current page
                if (/^[2-9]$|^[1-9][0-9]$/.test(text)) {
                    // Check if it's likely pagination by context
                    var parent = element.parentElement;
                    var grandParent = parent ? parent.parentElement : null;
                    
                    var isPagination = (
                        href.includes('page') || href.includes('p=') || 
                        onclick.includes('page') || onclick.includes('loadPage') ||
                        element.className.toLowerCase().includes('page') ||
                        (parent && parent.className.toLowerCase().includes('page')) ||
                        (grandParent && grandParent.className.toLowerCase().includes('page')) ||
                        element.getAttribute('data-page') ||
                        element.getAttribute('data-p')
                    );
                    
                    if (isPagination && element.offsetParent !== null) {
                        paginationLinks.push({
                            element: element,
                            text: text,
                            href: href,
                            onclick: onclick
                        });
                    }
                }
            }
            
            // Sort by page number
            paginationLinks.sort(function(a, b) {
                return parseInt(a.text) - parseInt(b.text);
            });
            
            return paginationLinks.slice(0, 10); // Return first 10 pagination links
            """
            
            pagination_data = driver.execute_script(pagination_script)
            
            if pagination_data:
                self.logger.info(f"📄 Found {len(pagination_data)} pagination elements")
                
                for page_info in pagination_data:
                    try:
                        page_text = page_info['text']
                        href = page_info['href']
                        onclick = page_info['onclick']
                        
                        self.logger.info(f"🔄 Clicking pagination page: '{page_text}'")
                        
                        # Get the actual element reference
                        element = driver.execute_script("""
                            var allElements = document.querySelectorAll('a, button, span[onclick], div[onclick]');
                            for (var i = 0; i < allElements.length; i++) {
                                var el = allElements[i];
                                if (el.textContent.trim() === arguments[0]) {
                                    return el;
                                }
                            }
                            return null;
                        """, page_text)
                        
                        if element:
                            # Scroll element into view
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                            time.sleep(1)
                            
                            # Click the pagination element
                            try:
                                driver.execute_script("arguments[0].click();", element)
                            except:
                                # Fallback: try direct click
                                element.click()
                            
                            # Wait for page to load
                            time.sleep(3)
                            
                            # Extract links from the new page
                            current_links = set(self.extract_links_from_driver(driver, url))
                            new_links = current_links - initial_links
                            
                            if new_links:
                                pagination_links.extend(list(new_links))
                                initial_links.update(new_links)
                                self.logger.info(f"🎯 Found {len(new_links)} new URLs from pagination page '{page_text}'")
                                
                                # Add these URLs to our dynamic discovery set
                                for link in new_links:
                                    self.dynamic_urls_found.add(link)
                            
                            # Go back to original page for next pagination click
                            driver.back()
                            time.sleep(2)
                            
                    except Exception as e:
                        self.logger.debug(f"Error clicking pagination page '{page_text}': {e}")
                        continue
            
            # Alternative approach: Look for pagination containers
            if not pagination_links:
                try:
                    # Find pagination containers and click numbered elements
                    pagination_containers = driver.find_elements(By.CSS_SELECTOR, 
                        ".pagination, .pager, .page-numbers, [class*='page'], [class*='paging']")
                    
                    for container in pagination_containers:
                        numbered_elements = container.find_elements(By.XPATH, 
                            ".//a[text()>='2' and text()<='20'] | .//button[text()>='2' and text()<='20']")
                        
                        for element in numbered_elements[:5]:  # Limit to 5 pages
                            try:
                                page_text = element.text.strip()
                                self.logger.info(f"🔄 Clicking container pagination: '{page_text}'")
                                
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                                time.sleep(1)
                                driver.execute_script("arguments[0].click();", element)
                                time.sleep(3)
                                
                                current_links = set(self.extract_links_from_driver(driver, url))
                                new_links = current_links - initial_links
                                
                                if new_links:
                                    pagination_links.extend(list(new_links))
                                    initial_links.update(new_links)
                                    self.logger.info(f"🎯 Found {len(new_links)} new URLs from container pagination '{page_text}'")
                                    
                                    for link in new_links:
                                        self.dynamic_urls_found.add(link)
                                
                                driver.back()
                                time.sleep(2)
                                
                            except Exception as e:
                                self.logger.debug(f"Error with container pagination: {e}")
                                continue
                        
                        if pagination_links:  # If we found pagination in this container, stop
                            break
                
                except Exception as e:
                    self.logger.debug(f"Error with container pagination: {e}")
            
            if pagination_links:
                self.logger.info(f"🎉 Pagination discovery complete: {len(pagination_links)} new URLs found!")
            else:
                self.logger.info("📄 No numbered pagination found on this page")
                
        except Exception as e:
            self.logger.error(f"Error in numbered pagination handling: {e}")
        
        return pagination_links

    def crawl_with_requests(self, url, depth):
        """Fast crawling using requests library"""
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract links
            links = []
            for link in soup.find_all('a', href=True):
                href = link['href']
                if href:
                    absolute_url = urljoin(url, href)
                    if self.is_valid_url(absolute_url):
                        links.append(absolute_url)
            
            page_data = {
                'url': url,
                'title': soup.title.string.strip() if soup.title else '',
                'depth': depth,
                'method': 'requests',
                'links_found': len(links),
                'links': list(set(links))[:15],
                'has_pagination': self.detect_pagination(soup),
                'has_dynamic_content': self.detect_dynamic_content(soup),
            }
            
            return page_data, links
            
        except Exception as e:
            self.logger.error(f"Error crawling {url} with requests: {e}")
            return None, []
    
    def crawl_with_selenium(self, url, depth):
        """Enhanced Selenium crawling with dynamic content discovery"""
        driver = self.create_selenium_driver()
        if not driver:
            return None, []
            
        try:
            driver.get(url)
            time.sleep(2)  # Wait for initial load
            
            # Get initial links
            initial_links = self.extract_links_from_driver(driver, url)
            
            # Discover dynamic content if enabled
            dynamic_links = []
            if self.dynamic_discovery:
                # First, try numbered pagination (most important for card layouts)
                pagination_links = self.handle_numbered_pagination(driver, url, set(initial_links))
                dynamic_links.extend(pagination_links)
                
                if dynamic_links:
                    self.logger.info(f"🔄 Found {len(dynamic_links)} additional URLs through pagination")
            
            all_links = list(set(initial_links + dynamic_links))
            
            page_data = {
                'url': url,
                'title': driver.title,
                'depth': depth,
                'method': 'selenium_enhanced' if dynamic_links else 'selenium',
                'links_found': len(all_links),
                'initial_links': len(initial_links),
                'dynamic_links': len(dynamic_links),
                'links': all_links[:20],
            }
            
            return page_data, all_links
            
        except Exception as e:
            self.logger.error(f"Error crawling {url} with Selenium: {e}")
            return None, []
        finally:
            driver.quit()
    
    def detect_pagination(self, soup):
        """Detect pagination elements"""
        pagination_indicators = ['next', 'prev', 'page', 'pagination']
        for indicator in pagination_indicators:
            if soup.find(attrs={'class': lambda x: x and indicator in x.lower()}):
                return True
        return False
        
    def detect_dynamic_content(self, soup):
        """Detect dynamic content indicators"""
        dynamic_indicators = ['load-more', 'show-more', 'carousel', 'slider', 'tab']
        for indicator in dynamic_indicators:
            if soup.find(attrs={'class': lambda x: x and indicator in x.lower()}):
                return True
        return len(soup.find_all('ul')) > 3
    
    def is_valid_url(self, url):
        """Check if URL is valid for crawling"""
        try:
            parsed = urlparse(url)
            
            if parsed.netloc and parsed.netloc != self.domain:
                return False
            
            skip_extensions = ['.pdf', '.jpg', '.jpeg', '.png', '.gif', '.zip', '.doc', '.docx']
            if any(url.lower().endswith(ext) for ext in skip_extensions):
                return False
            
            skip_paths = ['/admin', '/login', '/logout', '/api/', '/download']
            if any(path in url.lower() for path in skip_paths):
                return False
            
            return True
        except:
            return False
    
    def crawl_single_url(self, url, depth):
        """Crawl a single URL"""
        if len(self.crawled_data) >= self.max_pages:
            return []
        
        # Use Selenium for dynamic discovery or if it looks like it needs JS
        if self.dynamic_discovery or self.detect_needs_selenium(url):
            page_data, links = self.crawl_with_selenium(url, depth)
        else:
            # Try requests first for speed
            page_data, links = self.crawl_with_requests(url, depth)
        
        if page_data:
            with self.lock:
                if len(self.crawled_data) < self.max_pages:
                    self.crawled_data.append(page_data)
                    method = page_data.get('method', 'unknown')
                    dynamic_count = page_data.get('dynamic_links', 0)
                    dynamic_info = f" (+{dynamic_count} dynamic)" if dynamic_count > 0 else ""
                    self.logger.info(f"✓ Crawled: {url} (depth: {depth}) [{method}]{dynamic_info} - Page {len(self.crawled_data)}/{self.max_pages}")
                
                for link in links:
                    self.all_discovered_links.add(link)
        
        return links if self.exhaustive or depth < self.max_depth else []
    
    def detect_needs_selenium(self, url):
        """Detect if a URL likely needs Selenium for dynamic content"""
        dynamic_indicators = ['/search', '/category', '/products', '/articles', '/news', '/blog', '/insights']
        return any(indicator in url.lower() for indicator in dynamic_indicators)
    
    def crawl(self):
        """Main crawling method"""
        start_time = time.time()
        last_progress_report = 0
        
        self.logger.info(f"🚀 Starting {'exhaustive' if self.exhaustive else 'limited'} crawl with {'dynamic discovery' if self.dynamic_discovery else 'static only'}...")
        
        while self.url_queue and len(self.crawled_data) < self.max_pages:
            if len(self.crawled_data) - last_progress_report >= 10:
                self.logger.info(f"📊 Progress: {len(self.crawled_data)} pages crawled, {len(self.url_queue)} URLs in queue, {len(self.dynamic_urls_found)} dynamic URLs found")
                last_progress_report = len(self.crawled_data)
            
            # Process URLs in smaller batches for Selenium stability
            batch_size = min(2, len(self.url_queue))  # Smaller batches for Selenium
            current_batch = []
            
            for _ in range(batch_size):
                if self.url_queue:
                    url, depth = self.url_queue.pop(0)
                    if url not in self.visited_urls:
                        self.visited_urls.add(url)
                        current_batch.append((url, depth))
            
            if not current_batch:
                break
            
            # Process batch with limited concurrency for Selenium stability
            max_workers = 1 if self.dynamic_discovery else 2  # Sequential for dynamic discovery
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_url = {
                    executor.submit(self.crawl_single_url, url, depth): (url, depth)
                    for url, depth in current_batch
                }
                
                for future in concurrent.futures.as_completed(future_to_url):
                    new_links = future.result()
                    
                    for link in new_links:
                        if (link not in self.visited_urls and 
                            link not in [queued_url for queued_url, _ in self.url_queue] and
                            len(self.crawled_data) < self.max_pages):
                            
                            url, depth = future_to_url[future]
                            if self.exhaustive or depth + 1 <= self.max_depth:
                                self.url_queue.append((link, depth + 1))
        
        end_time = time.time()
        self.logger.info(f"🎉 Crawling completed in {end_time - start_time:.2f} seconds")
        return self.crawled_data
    
    def save_urls_only(self, filename='crawled_urls.json'):
        """Save only unique URLs in compact format"""
        urls_data = {
            'base_url': self.base_url,
            'total_urls_found': len(self.visited_urls),
            'dynamic_urls_found': len(self.dynamic_urls_found),
            'crawl_timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'unique_urls': sorted(list(self.visited_urls)),
            'dynamic_urls': sorted(list(self.dynamic_urls_found)) if self.dynamic_urls_found else []
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(urls_data, f, indent=2, ensure_ascii=False)
        self.logger.info(f"🔗 URLs-only data saved to {filename}")
    
    def get_summary(self):
        """Get crawling summary"""
        if not self.crawled_data:
            return {"error": "No data crawled"}
        
        total_pages = len(self.crawled_data)
        total_links = sum(page.get('links_found', 0) for page in self.crawled_data)
        dynamic_pages = sum(1 for page in self.crawled_data if page.get('dynamic_links', 0) > 0)
        
        methods_used = {}
        for page in self.crawled_data:
            method = page.get('method', 'unknown')
            methods_used[method] = methods_used.get(method, 0) + 1
        
        return {
            'total_pages_crawled': total_pages,
            'total_links_found': total_links,
            'dynamic_urls_discovered': len(self.dynamic_urls_found),
            'pages_with_dynamic_content': dynamic_pages,
            'max_depth_reached': max(page.get('depth', 0) for page in self.crawled_data),
            'unique_urls_visited': len(self.visited_urls),
            'methods_used': methods_used,
        }

if __name__ == "__main__":
    print("🚀 Enhanced Web Crawler - Pagination-Aware Edition")
    print("=" * 60)
    
    base_url = input("Enter the base URL to crawl: ").strip()
    
    print("\nCrawling Mode:")
    print("1. Exhaustive (crawl ALL discoverable pages until none left)")
    print("2. Limited (respect depth and page limits)")
    mode = input("Choose mode (1/2, default 1): ").strip() or "1"
    exhaustive = mode == "1"
    
    if exhaustive:
        max_pages = int(input("Enter max pages to crawl (default 200): ") or 200)
        max_depth = 999
        print("🔥 EXHAUSTIVE MODE: Will crawl until all discoverable pages are found!")
    else:
        max_pages = int(input("Enter max pages to crawl (default 50): ") or 50)
        max_depth = int(input("Enter max depth (default 3): ") or 3)
        print("⚡ LIMITED MODE: Will respect depth and page limits")
    
    print("\nDynamic Content Discovery:")
    print("1. Yes (click numbered pagination 1,2,3,4... to discover card URLs)")
    print("2. No (only static content)")
    dynamic_choice = input("Enable pagination discovery? (1/2, default 1): ").strip() or "1"
    dynamic_discovery = dynamic_choice == "1"
    
    if dynamic_discovery:
        print("🔄 PAGINATION MODE: Will click through numbered pages to discover all card URLs!")
    else:
        print("📄 STATIC MODE: Will only crawl visible links")
    
    crawler = EnhancedWebCrawler(
        base_url=base_url,
        max_depth=max_depth,
        max_pages=max_pages,
        use_selenium=True,  # Always use Selenium for dynamic discovery
        exhaustive=exhaustive,
        dynamic_discovery=dynamic_discovery
    )
    
    print(f"\n🔍 Starting {'EXHAUSTIVE' if exhaustive else 'LIMITED'} crawl of {base_url}")
    print(f"📊 Max pages: {max_pages}" + (f", Max depth: {max_depth}" if not exhaustive else " (unlimited depth)"))
    print(f"🔄 Pagination: {'YES - Will click through numbered pages' if dynamic_discovery else 'NO - Static only'}")
    print("=" * 60)
    
    crawled_data = crawler.crawl()
    
    # Save results
    crawler.save_urls_only()
    print(f"\n🔗 Saved {len(crawler.visited_urls)} unique URLs to crawled_urls.json")
    
    # Print summary
    summary = crawler.get_summary()
    print("\n📈 Crawl Summary:")
    print("=" * 60)
    print(json.dumps(summary, indent=2))
    
    if exhaustive:
        print(f"\n🎉 EXHAUSTIVE CRAWL COMPLETE!")
        print(f"🔍 Discovered and visited ALL {len(crawler.visited_urls)} unique URLs")
        print(f"📄 Successfully crawled {len(crawled_data)} pages")
        
        if dynamic_discovery and crawler.dynamic_urls_found:
            print(f"🎯 Pagination discovery found {len(crawler.dynamic_urls_found)} additional URLs!")
            print("Sample pagination URLs:")
            for url in list(crawler.dynamic_urls_found)[:5]:
                print(f"  • {url}")