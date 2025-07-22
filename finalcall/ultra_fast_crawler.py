import json
import time
import logging
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import concurrent.futures
import threading

class UltraFastCrawler:
    def __init__(self, base_url, max_depth=5, max_pages=200, use_selenium=True, exhaustive=True, dynamic_discovery=True):
        self.base_url = base_url
        self.domain = urlparse(base_url).netloc
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.use_selenium = use_selenium
        self.exhaustive = exhaustive  # If True, crawl until no new pages found
        self.dynamic_discovery = dynamic_discovery  # If True, discover dynamic content
        self.visited_urls = set()
        self.crawled_data = []
        self.url_queue = [(base_url, 0)]
        self.lock = threading.Lock()
        self.all_discovered_links = set()  # Track all discovered links
        self.dynamic_urls_found = set()  # Track URLs found through dynamic interactions
        
        # Setup session for requests
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
    def create_selenium_driver(self):
        """Create minimal Selenium driver only when needed"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-images")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-logging")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-client-side-phishing-detection")
        chrome_options.add_argument("--disable-sync")
        chrome_options.add_argument("--disable-default-apps")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--no-default-browser-check")
        
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.set_page_load_timeout(10)
            driver.implicitly_wait(1)
            return driver
        except Exception as e:
            self.logger.error(f"Failed to create Selenium driver: {e}")
            return None
    
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
            
            # Extract page data
            page_data = {
                'url': url,
                'title': soup.title.string.strip() if soup.title else '',
                'depth': depth,
                'method': 'requests',
                'links_found': len(links),
                'links': list(set(links))[:15],  # Remove duplicates, limit to 15
                'has_pagination': self.detect_pagination(soup),
                'has_dynamic_content': self.detect_dynamic_content(soup),
                'headings': {
                    'h1': [h.get_text().strip() for h in soup.find_all('h1')[:5]],
                    'h2': [h.get_text().strip() for h in soup.find_all('h2')[:5]],
                    'h3': [h.get_text().strip() for h in soup.find_all('h3')[:3]]
                },
                'meta_description': '',
                'forms': len(soup.find_all('form')),
                'images': len(soup.find_all('img')),
                'lists': len(soup.find_all('ul')) + len(soup.find_all('ol'))
            }
            
            # Get meta description
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc:
                page_data['meta_description'] = meta_desc.get('content', '')[:200]
            
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
            time.sleep(1)  # Wait for initial load
            
            # Get initial links
            initial_links = self.extract_links_from_driver(driver, url)
            
            # If dynamic discovery is enabled, interact with dynamic elements
            dynamic_links = []
            if self.dynamic_discovery:
                dynamic_links = self.discover_dynamic_content(driver, url)
                self.logger.info(f"🔄 Found {len(dynamic_links)} additional URLs through dynamic interactions on {url}")
            
            # Combine all links
            all_links = list(set(initial_links + dynamic_links))
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            js_interactions = self.detect_js_interactions(driver)
            
            page_data = {
                'url': url,
                'title': driver.title,
                'depth': depth,
                'method': 'selenium_enhanced',
                'links_found': len(all_links),
                'initial_links': len(initial_links),
                'dynamic_links': len(dynamic_links),
                'links': list(set(all_links))[:20],  # Show more links since we found more
                'has_pagination': self.detect_pagination(soup),
                'has_dynamic_content': self.detect_dynamic_content(soup),
                'js_interactions': js_interactions,
                'headings': {
                    'h1': [h.get_text().strip() for h in soup.find_all('h1')[:5]],
                    'h2': [h.get_text().strip() for h in soup.find_all('h2')[:5]]
                }
            }
            
            # Track dynamic URLs separately
            for link in dynamic_links:
                self.dynamic_urls_found.add(link)
            
            return page_data, all_links
            
        except Exception as e:
            self.logger.error(f"Error crawling {url} with Selenium: {e}")
            return None, []
        finally:
            driver.quit()
    
    def detect_pagination(self, soup):
        """Detect pagination elements"""
        pagination_selectors = [
            'a[href*="page"]', 'a[href*="next"]', 'a[href*="prev"]',
            '.pagination', '.pager', '.page-numbers',
            'button[class*="next"]', 'button[class*="prev"]'
        ]
        
        for selector in pagination_selectors:
            if soup.select(selector):
                return True
        
        # Text-based detection
        pagination_text = ['next', 'previous', 'prev', '→', '←', '»', '«']
        for text in pagination_text:
            if soup.find(string=lambda t: t and text.lower() in t.lower()):
                return True
        
        return False
    
    def detect_dynamic_content(self, soup):
        """Detect dynamic content indicators"""
        dynamic_selectors = [
            '.load-more', '.show-more', '.carousel', '.slider',
            '.tabs', '.accordion', '[data-toggle]', '[onclick]'
        ]
        
        for selector in dynamic_selectors:
            if soup.select(selector):
                return True
        
        # Check for many list items (potential dynamic content)
        ul_elements = soup.find_all('ul')
        for ul in ul_elements:
            if len(ul.find_all('li')) > 10:
                return True
        
        return False
    
    def extract_links_from_driver(self, driver, base_url):
        """Extract all links from current driver state"""
        links = []
        try:
            link_elements = driver.find_elements("css selector", "a[href]")
            for link in link_elements:
                href = link.get_attribute('href')
                if href:
                    absolute_url = urljoin(base_url, href)
                    if self.is_valid_url(absolute_url):
                        links.append(absolute_url)
        except Exception as e:
            self.logger.debug(f"Error extracting links: {e}")
        return links

    def discover_dynamic_content(self, driver, url):
        """Discover URLs from dynamically loaded content by interacting with page elements"""
        dynamic_links = []
        max_interactions = 25  # Increased limit for pagination
        interaction_count = 0
        
        try:
            # Get initial page state
            initial_links = set(self.extract_links_from_driver(driver, url))
            self.logger.info(f"🔍 Starting with {len(initial_links)} initial links on {url}")
            
            # First, try to find and click through pagination (numbered pages)
            pagination_links = self.handle_numbered_pagination(driver, url, initial_links)
            dynamic_links.extend(pagination_links)
            interaction_count += len(pagination_links) // 10  # Rough estimate
            
            # Then try other interactive elements
            interactive_selectors = [
                # Pagination buttons (more specific)
                "a[href*='page='], button[data-page]",
                "a[href*='p='], button[data-p]",
                ".pagination a, .pagination button",
                ".pager a, .pager button", 
                ".page-numbers a, .page-numbers button",
                
                # Next/Previous buttons
                "button:contains('Next'), a:contains('Next')",
                "button:contains('Previous'), a:contains('Previous')",
                "button[class*='next'], a[class*='next']",
                "button[class*='prev'], a[class*='prev']",
                
                # Load more buttons
                "button:contains('Load More'), a:contains('Load More')",
                "button:contains('Show More'), a:contains('Show More')",
                "button[class*='load'], a[class*='load']",
                "button[class*='more'], a[class*='more']",
                ".load-more, .show-more",
                
                # Card containers that might have hidden content
                ".card a, .item a, .post a",
                ".article a, .blog-post a",
                
                # Tab and accordion controls
                "button[role='tab'], a[role='tab']",
                ".tab button, .tab a",
                ".tabs button, .tabs a",
                ".accordion button",
                
                # Generic interactive elements
                "button[onclick], a[onclick]",
                "button[data-toggle], a[data-toggle]",
                "[data-load], [data-more]"
            ]
            
            # Try each selector type
            for selector in interactive_selectors:
                if interaction_count >= max_interactions:
                    break
                    
                try:
                    elements = driver.find_elements("css selector", selector)
                    self.logger.debug(f"Found {len(elements)} elements for selector: {selector}")
                    
                    for element in elements[:3]:  # Limit to 3 elements per selector
                        if interaction_count >= max_interactions:
                            break
                            
                        try:
                            # Check if element is visible and clickable
                            if not element.is_displayed() or not element.is_enabled():
                                continue
                                
                            # Get element info for logging
                            element_text = element.text.strip()[:30]
                            element_class = element.get_attribute('class') or ''
                            
                            # Skip if it looks like it will navigate away from page
                            href = element.get_attribute('href')
                            if href and not href.startswith('#') and not href.startswith('javascript:'):
                                continue
                                
                            self.logger.debug(f"Attempting to click: {element_text} (class: {element_class})")
                            
                            # Scroll element into view
                            driver.execute_script("arguments[0].scrollIntoView(true);", element)
                            time.sleep(0.5)
                            
                            # Click the element
                            driver.execute_script("arguments[0].click();", element)
                            interaction_count += 1
                            
                            # Wait for content to load
                            time.sleep(2)
                            
                            # Check for new links
                            current_links = set(self.extract_links_from_driver(driver, url))
                            new_links = current_links - initial_links
                            
                            if new_links:
                                dynamic_links.extend(list(new_links))
                                initial_links.update(new_links)
                                self.logger.info(f"🎯 Found {len(new_links)} new URLs after clicking '{element_text}'")
                            
                            # Look for "Next" or "Load More" patterns to continue clicking
                            if any(keyword in element_text.lower() for keyword in ['next', 'more', 'load']):
                                # Try clicking multiple times for pagination
                                for _ in range(3):  # Try up to 3 more clicks
                                    if interaction_count >= max_interactions:
                                        break
                                        
                                    try:
                                        # Check if element is still clickable
                                        if not element.is_displayed() or not element.is_enabled():
                                            break
                                            
                                        driver.execute_script("arguments[0].click();", element)
                                        interaction_count += 1
                                        time.sleep(2)
                                        
                                        # Check for more new links
                                        current_links = set(self.extract_links_from_driver(driver, url))
                                        new_links = current_links - initial_links
                                        
                                        if new_links:
                                            dynamic_links.extend(list(new_links))
                                            initial_links.update(new_links)
                                            self.logger.info(f"🎯 Found {len(new_links)} more URLs after additional click")
                                        else:
                                            break  # No more new content
                                            
                                    except Exception as e:
                                        self.logger.debug(f"Error in repeated click: {e}")
                                        break
                            
                        except Exception as e:
                            self.logger.debug(f"Error clicking element: {e}")
                            continue
                            
                except Exception as e:
                    self.logger.debug(f"Error with selector {selector}: {e}")
                    continue
            
            # Also check for infinite scroll content
            dynamic_links.extend(self.handle_infinite_scroll(driver, url))
            
        except Exception as e:
            self.logger.error(f"Error in dynamic content discovery: {e}")
        
        return list(set(dynamic_links))  # Remove duplicates
    
    def handle_numbered_pagination(self, driver, url, initial_links):
        """Handle numbered pagination (1, 2, 3, 4, ..., 8) like in the screenshot"""
        pagination_links = []
        
        try:
            self.logger.info(f"🔢 Looking for numbered pagination on {url}")
            
            # Look for numbered pagination elements using multiple strategies
            pagination_strategies = [
                # Strategy 1: Find numbered links/buttons
                "//a[text()='2'] | //button[text()='2'] | //span[text()='2']/../a | //span[text()='2']/../button",
                "//a[text()='3'] | //button[text()='3'] | //span[text()='3']/../a | //span[text()='3']/../button",
                "//a[text()='4'] | //button[text()='4'] | //span[text()='4']/../a | //span[text()='4']/../button",
                
                # Strategy 2: Find pagination containers and look for numbers
                "//*[contains(@class, 'pagination')]//a[string-length(text()) <= 2 and text() != '1']",
                "//*[contains(@class, 'pager')]//a[string-length(text()) <= 2 and text() != '1']",
                "//*[contains(@class, 'page')]//a[string-length(text()) <= 2 and text() != '1']",
                
                # Strategy 3: Look for href patterns with page numbers
                "//a[contains(@href, 'page=') and not(contains(@href, 'page=1'))]",
                "//a[contains(@href, 'p=') and not(contains(@href, 'p=1'))]",
                "//a[contains(@href, '/page/') and not(contains(@href, '/page/1'))]",
            ]
            
            found_pagination = False
            
            for strategy in pagination_strategies:
                try:
                    elements = driver.find_elements("xpath", strategy)
                    if elements:
                        self.logger.info(f"📄 Found {len(elements)} pagination elements with strategy: {strategy}")
                        found_pagination = True
                        
                        # Click through each pagination element
                        for element in elements[:10]:  # Limit to first 10 pages
                            try:
                                if not element.is_displayed() or not element.is_enabled():
                                    continue
                                
                                page_text = element.text.strip()
                                href = element.get_attribute('href')
                                
                                self.logger.info(f"🔄 Clicking pagination: '{page_text}' (href: {href})")
                                
                                # Scroll element into view
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                                time.sleep(1)
                                
                                # Click the pagination element
                                try:
                                    element.click()
                                except:
                                    driver.execute_script("arguments[0].click();", element)
                                
                                # Wait for page to load
                                time.sleep(3)
                                
                                # Extract links from the new page
                                current_links = set(self.extract_links_from_driver(driver, url))
                                new_links = current_links - initial_links
                                
                                if new_links:
                                    pagination_links.extend(list(new_links))
                                    initial_links.update(new_links)
                                    self.logger.info(f"🎯 Found {len(new_links)} new URLs from pagination page '{page_text}'")
                                
                                # Go back to original page for next pagination click
                                driver.back()
                                time.sleep(2)
                                
                            except Exception as e:
                                self.logger.debug(f"Error clicking pagination element: {e}")
                                continue
                        
                        break  # If we found pagination with one strategy, don't try others
                        
                except Exception as e:
                    self.logger.debug(f"Error with pagination strategy: {e}")
                    continue
            
            # Alternative approach: Use JavaScript to find and click pagination
            if not found_pagination:
                try:
                    self.logger.info("🔍 Trying JavaScript-based pagination detection...")
                    
                    # JavaScript to find pagination elements
                    pagination_script = """
                    var paginationLinks = [];
                    var allLinks = document.querySelectorAll('a, button');
                    
                    for (var i = 0; i < allLinks.length; i++) {
                        var element = allLinks[i];
                        var text = element.textContent.trim();
                        var href = element.href || '';
                        
                        // Look for numbered pagination (2, 3, 4, etc.)
                        if (/^[2-9]$|^[1-9][0-9]$/.test(text) && 
                            (href.includes('page') || href.includes('p=') || 
                             element.className.includes('page') || 
                             element.parentElement.className.includes('page'))) {
                            paginationLinks.push(element);
                        }
                    }
                    
                    return paginationLinks.slice(0, 8); // Return first 8 pagination links
                    """
                    
                    pagination_elements = driver.execute_script(pagination_script)
                    
                    if pagination_elements:
                        self.logger.info(f"📄 Found {len(pagination_elements)} pagination elements via JavaScript")
                        
                        for element in pagination_elements:
                            try:
                                page_text = element.text.strip()
                                self.logger.info(f"🔄 Clicking JS pagination: '{page_text}'")
                                
                                # Click using JavaScript
                                driver.execute_script("arguments[0].click();", element)
                                time.sleep(3)
                                
                                # Extract new links
                                current_links = set(self.extract_links_from_driver(driver, url))
                                new_links = current_links - initial_links
                                
                                if new_links:
                                    pagination_links.extend(list(new_links))
                                    initial_links.update(new_links)
                                    self.logger.info(f"🎯 Found {len(new_links)} new URLs from JS pagination '{page_text}'")
                                
                                # Go back
                                driver.back()
                                time.sleep(2)
                                
                            except Exception as e:
                                self.logger.debug(f"Error with JS pagination: {e}")
                                continue
                
                except Exception as e:
                    self.logger.debug(f"Error with JavaScript pagination: {e}")
            
            if pagination_links:
                self.logger.info(f"🎉 Total pagination discovery: {len(pagination_links)} new URLs found!")
            else:
                self.logger.info("📄 No pagination found on this page")
                
        except Exception as e:
            self.logger.error(f"Error in numbered pagination handling: {e}")
        
        return pagination_links

    def handle_infinite_scroll(self, driver, url):
        """Handle infinite scroll to discover more content"""
        scroll_links = []
        try:
            initial_height = driver.execute_script("return document.body.scrollHeight")
            initial_links = set(self.extract_links_from_driver(driver, url))
            
            # Try scrolling down multiple times
            for scroll_attempt in range(5):  # Limit scroll attempts
                # Scroll to bottom
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)  # Wait for content to load
                
                # Check if page height increased (new content loaded)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height > initial_height:
                    # Get new links
                    current_links = set(self.extract_links_from_driver(driver, url))
                    new_links = current_links - initial_links
                    
                    if new_links:
                        scroll_links.extend(list(new_links))
                        initial_links.update(new_links)
                        self.logger.info(f"📜 Found {len(new_links)} URLs through infinite scroll")
                    
                    initial_height = new_height
                else:
                    break  # No more content to load
                    
        except Exception as e:
            self.logger.debug(f"Error in infinite scroll handling: {e}")
        
        return scroll_links

    def detect_js_interactions(self, driver):
        """Detect JavaScript interactions using Selenium"""
        interactions = []
        
        try:
            # Look for buttons that might load content
            buttons = driver.find_elements("css selector", "button, .btn, [onclick], [data-toggle]")
            for button in buttons[:5]:  # Limit to first 5
                if button.is_displayed():
                    interactions.append({
                        'type': 'button',
                        'text': button.text[:50],
                        'class': button.get_attribute('class')
                    })
        except:
            pass
        
        return interactions
    
    def is_valid_url(self, url):
        """Check if URL is valid for crawling"""
        try:
            parsed = urlparse(url)
            
            # Same domain check
            if parsed.netloc and parsed.netloc != self.domain:
                return False
            
            # Skip certain file types
            skip_extensions = ['.pdf', '.jpg', '.jpeg', '.png', '.gif', '.zip', '.doc', '.docx', '.xls', '.xlsx']
            if any(url.lower().endswith(ext) for ext in skip_extensions):
                return False
            
            # Skip certain paths
            skip_paths = ['/admin', '/login', '/logout', '/api/', '/download']
            if any(path in url.lower() for path in skip_paths):
                return False
            
            return True
        except:
            return False
    
    def crawl_single_url(self, url, depth):
        """Crawl a single URL and return all discovered links"""
        if len(self.crawled_data) >= self.max_pages:
            return []
        
        # Try requests first (faster)
        page_data, links = self.crawl_with_requests(url, depth)
        
        # If requests failed and Selenium is enabled, try Selenium
        if not page_data and self.use_selenium:
            page_data, links = self.crawl_with_selenium(url, depth)
        
        if page_data:
            with self.lock:
                if len(self.crawled_data) < self.max_pages:
                    self.crawled_data.append(page_data)
                    self.logger.info(f"✓ Crawled: {url} (depth: {depth}) - Page {len(self.crawled_data)}/{self.max_pages}")
                
                # Add all discovered links to our tracking set
                for link in links:
                    self.all_discovered_links.add(link)
        
        # Return links for further crawling (respect depth limit unless exhaustive mode)
        if self.exhaustive:
            return links  # In exhaustive mode, ignore depth limit
        else:
            return links if depth < self.max_depth else []
    
    def crawl(self):
        """Main crawling method with complete recursive crawling"""
        start_time = time.time()
        last_progress_report = 0
        
        self.logger.info(f"🚀 Starting {'exhaustive' if self.exhaustive else 'limited'} crawl...")
        
        while self.url_queue and len(self.crawled_data) < self.max_pages:
            # Progress reporting
            if len(self.crawled_data) - last_progress_report >= 10:
                self.logger.info(f"📊 Progress: {len(self.crawled_data)} pages crawled, {len(self.url_queue)} URLs in queue, {len(self.all_discovered_links)} total links discovered")
                last_progress_report = len(self.crawled_data)
            
            # Process URLs in batches for better performance
            batch_size = min(5, len(self.url_queue))
            current_batch = []
            
            for _ in range(batch_size):
                if self.url_queue:
                    url, depth = self.url_queue.pop(0)
                    if url not in self.visited_urls:
                        self.visited_urls.add(url)
                        current_batch.append((url, depth))
            
            if not current_batch:
                break
            
            # Process batch with threading
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                future_to_url = {
                    executor.submit(self.crawl_single_url, url, depth): (url, depth)
                    for url, depth in current_batch
                }
                
                for future in concurrent.futures.as_completed(future_to_url):
                    new_links = future.result()
                    url, depth = future_to_url[future]
                    
                    # Add new links to queue for recursive crawling
                    new_links_added = 0
                    for link in new_links:
                        if (link not in self.visited_urls and 
                            link not in [queued_url for queued_url, _ in self.url_queue] and
                            len(self.crawled_data) < self.max_pages):
                            
                            # In exhaustive mode, keep crawling regardless of depth
                            # In limited mode, respect depth limit
                            if self.exhaustive or depth + 1 <= self.max_depth:
                                self.url_queue.append((link, depth + 1))
                                new_links_added += 1
                    
                    if new_links_added > 0:
                        self.logger.debug(f"Added {new_links_added} new URLs to queue from {url}")
        
        # Final check - if exhaustive mode and we have undiscovered links, add them
        if self.exhaustive and len(self.crawled_data) < self.max_pages:
            remaining_links = self.all_discovered_links - self.visited_urls
            if remaining_links:
                self.logger.info(f"🔍 Found {len(remaining_links)} additional undiscovered links, adding to queue...")
                for link in list(remaining_links)[:50]:  # Add up to 50 more
                    if len(self.crawled_data) < self.max_pages:
                        self.url_queue.append((link, 999))  # High depth number for final sweep
                
                # Process remaining links
                while self.url_queue and len(self.crawled_data) < self.max_pages:
                    url, depth = self.url_queue.pop(0)
                    if url not in self.visited_urls:
                        self.visited_urls.add(url)
                        page_data, links = self.crawl_with_requests(url, depth)
                        if page_data:
                            with self.lock:
                                if len(self.crawled_data) < self.max_pages:
                                    self.crawled_data.append(page_data)
                                    self.logger.info(f"✓ Final sweep: {url} - Page {len(self.crawled_data)}/{self.max_pages}")
        
        end_time = time.time()
        self.logger.info(f"🎉 Crawling completed in {end_time - start_time:.2f} seconds")
        self.logger.info(f"📈 Final stats: {len(self.crawled_data)} pages crawled, {len(self.visited_urls)} URLs visited, {len(self.all_discovered_links)} total links discovered")
        return self.crawled_data
    
    def save_to_json(self, filename='ultra_fast_crawled_data.json'):
        """Save results to JSON"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.crawled_data, f, indent=2, ensure_ascii=False)
        self.logger.info(f"💾 Data saved to {filename}")
    
    def save_urls_only(self, filename='crawled_urls.json'):
        """Save only unique URLs in compact format"""
        urls_data = {
            'base_url': self.base_url,
            'total_urls_found': len(self.visited_urls),
            'crawl_timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'unique_urls': sorted(list(self.visited_urls))
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
        pages_with_pagination = sum(1 for page in self.crawled_data if page.get('has_pagination', False))
        pages_with_dynamic = sum(1 for page in self.crawled_data if page.get('has_dynamic_content', False))
        
        methods_used = {}
        for page in self.crawled_data:
            method = page.get('method', 'unknown')
            methods_used[method] = methods_used.get(method, 0) + 1
        
        return {
            'total_pages_crawled': total_pages,
            'total_links_found': total_links,
            'pages_with_pagination': pages_with_pagination,
            'pages_with_dynamic_content': pages_with_dynamic,
            'max_depth_reached': max(page.get('depth', 0) for page in self.crawled_data),
            'unique_urls_visited': len(self.visited_urls),
            'methods_used': methods_used,
            'sample_titles': [page.get('title', '')[:50] for page in self.crawled_data[:5]]
        }

if __name__ == "__main__":
    print("🚀 Ultra Fast Web Crawler - Recursive Edition")
    print("=" * 50)
    
    base_url = input("Enter the base URL to crawl: ").strip()
    
    # Crawling mode selection
    print("\nCrawling Mode:")
    print("1. Exhaustive (crawl ALL discoverable pages until none left)")
    print("2. Limited (respect depth and page limits)")
    mode = input("Choose mode (1/2, default 1): ").strip() or "1"
    exhaustive = mode == "1"
    
    if exhaustive:
        max_pages = int(input("Enter max pages to crawl (default 200): ") or 200)
        max_depth = 999  # Effectively unlimited in exhaustive mode
        print("� EXHAiUSTIVE MODE: Will crawl until all discoverable pages are found!")
    else:
        max_pages = int(input("Enter max pages to crawl (default 50): ") or 50)
        max_depth = int(input("Enter max depth (default 3): ") or 3)
        print("⚡ LIMITED MODE: Will respect depth and page limits")
    
    # Dynamic content discovery option
    print("\nDynamic Content Discovery:")
    print("1. Yes (find URLs from Next/Prev buttons, Load More, infinite scroll)")
    print("2. No (only static content)")
    dynamic_choice = input("Enable dynamic discovery? (1/2, default 1): ").strip() or "1"
    dynamic_discovery = dynamic_choice == "1"
    
    # Selenium is required for dynamic discovery
    if dynamic_discovery:
        use_selenium = True
        print("🔄 DYNAMIC MODE: Will interact with buttons and discover hidden URLs!")
    else:
        use_selenium = input("Use Selenium for JS-heavy sites? (y/n, default n): ").lower().startswith('y')
    
    crawler = UltraFastCrawler(
        base_url=base_url, 
        max_depth=max_depth, 
        max_pages=max_pages,
        use_selenium=use_selenium,
        exhaustive=exhaustive,
        dynamic_discovery=dynamic_discovery
    )
    
    print(f"\n🔍 Starting {'EXHAUSTIVE' if exhaustive else 'LIMITED'} crawl of {base_url}")
    print(f"📊 Max pages: {max_pages}" + (f", Max depth: {max_depth}" if not exhaustive else " (unlimited depth)"))
    print(f"⚡ Method: {'Requests + Selenium' if use_selenium else 'Requests only'}")
    print(f"🎯 Mode: {'Crawl ALL discoverable pages' if exhaustive else 'Respect limits'}")
    print(f"🔄 Dynamic: {'YES - Will click buttons/pagination' if dynamic_discovery else 'NO - Static only'}")
    print("=" * 50)
    
    crawled_data = crawler.crawl()
    
    # Ask user what format they want
    print("\nOutput Format:")
    print("1. URLs only (compact, just the unique URLs)")
    print("2. Full data (detailed page information)")
    output_choice = input("Choose output format (1/2, default 1): ").strip() or "1"
    
    if output_choice == "1":
        # Save only URLs
        crawler.save_urls_only()
        print(f"\n🔗 Saved {len(crawler.visited_urls)} unique URLs to crawled_urls.json")
    else:
        # Save full data
        crawler.save_to_json()
        print(f"💾 Saved full crawl data to ultra_fast_crawled_data.json")
    
    # Print summary
    summary = crawler.get_summary()
    print("\n📈 Crawl Summary:")
    print("=" * 50)
    print(json.dumps(summary, indent=2))
    
    if exhaustive:
        print(f"\n🎉 EXHAUSTIVE CRAWL COMPLETE!")
        print(f"🔍 Discovered and visited ALL {len(crawler.visited_urls)} unique URLs")
        print(f"📄 Successfully crawled {len(crawled_data)} pages")
        print(f"🔗 Found {len(crawler.all_discovered_links)} total unique links")
        
        if dynamic_discovery and crawler.dynamic_urls_found:
            print(f"🎯 Dynamic discovery found {len(crawler.dynamic_urls_found)} additional URLs!")
            print("Sample dynamic URLs:")
            for url in list(crawler.dynamic_urls_found)[:5]:
                print(f"  • {url}")
    
    print(f"\n🔍 Starting {'EXHAUSTIVE' if exhaustive else 'LIMITED'} crawl of {base_url}")
    print(f"📊 Max pages: {max_pages}" + (f", Max depth: {max_depth}" if not exhaustive else " (unlimited depth)"))
    print(f"⚡ Method: {'Requests + Selenium' if use_selenium else 'Requests only'}")
    print(f"🎯 Mode: {'Crawl ALL discoverable pages' if exhaustive else 'Respect limits'}")
    print("=" * 50)
    
    crawled_data = crawler.crawl()
    
    # Ask user what format they want
    print("\nOutput Format:")
    print("1. URLs only (compact, just the unique URLs)")
    print("2. Full data (detailed page information)")
    output_choice = input("Choose output format (1/2, default 1): ").strip() or "1"
    
    if output_choice == "1":
        # Save only URLs
        crawler.save_urls_only()
        print(f"\n🔗 Saved {len(crawler.visited_urls)} unique URLs to crawled_urls.json")
    else:
        # Save full data
        crawler.save_to_json()
        print(f"💾 Saved full crawl data to ultra_fast_crawled_data.json")
    
    # Print summary
    summary = crawler.get_summary()
    print("\n📈 Crawl Summary:")
    print("=" * 50)
    print(json.dumps(summary, indent=2))
    
    if exhaustive:
        print(f"\n🎉 EXHAUSTIVE CRAWL COMPLETE!")
        print(f"🔍 Discovered and visited ALL {len(crawler.visited_urls)} unique URLs")
        print(f"📄 Successfully crawled {len(crawled_data)} pages")
        print(f"🔗 Found {len(crawler.all_discovered_links)} total unique links")
        dynamic_discovery=dynamic_discovery
    )
    
    print(f"\n🔍 Starting {'EXHAUSTIVE' if exhaustive else 'LIMITED'} crawl of {base_url}")
    print(f"📊 Max pages: {max_pages}" + (f", Max depth: {max_depth}" if not exhaustive else " (unlimited depth)"))
    print(f"⚡ Method: {'Requests + Selenium' if use_selenium else 'Requests only'}")
    print(f"🎯 Mode: {'Crawl ALL discoverable pages' if exhaustive else 'Respect limits'}")
    print(f"🔄 Dynamic: {'YES - Will click buttons/pagination' if dynamic_discovery else 'NO - Static only'}")
    print("=" * 50)
    
    crawled_data = crawler.crawl()
    
    # Ask user what format they want
    print("\nOutput Format:")
    print("1. URLs only (compact, just the unique URLs)")
    print("2. Full data (detailed page information)")
    output_choice = input("Choose output format (1/2, default 1): ").strip() or "1"
    
    if output_choice == "1":
        # Save only URLs
        crawler.save_urls_only()
        print(f"\n🔗 Saved {len(crawler.visited_urls)} unique URLs to crawled_urls.json")
    else:
        # Save full data
        crawler.save_to_json()
        print(f"💾 Saved full crawl data to ultra_fast_crawled_data.json")
    
    # Print summary
    summary = crawler.get_summary()
    print("\n📈 Crawl Summary:")
    print("=" * 50)
    print(json.dumps(summary, indent=2))
    
    if exhaustive:
        print(f"\n🎉 EXHAUSTIVE CRAWL COMPLETE!")
        print(f"🔍 Discovered and visited ALL {len(crawler.visited_urls)} unique URLs")
        print(f"📄 Successfully crawled {len(crawled_data)} pages")
        print(f"🔗 Found {len(crawler.all_discovered_links)} total unique links")
        
        if dynamic_discovery and crawler.dynamic_urls_found:
            print(f"🎯 Dynamic discovery found {len(crawler.dynamic_urls_found)} additional URLs!")
            print("Sample dynamic URLs:")
            for url in list(crawler.dynamic_urls_found)[:5]:
                print(f"  • {url}")