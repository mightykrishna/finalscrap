import json
import time
import logging
from urllib.parse import urljoin, urlparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import requests
import os

class WebCrawler:
    def __init__(self, base_url, max_depth=2, delay=0.5, max_pages=50):
        self.base_url = base_url
        self.domain = urlparse(base_url).netloc
        self.max_depth = max_depth
        self.delay = delay
        self.max_pages = max_pages
        self.visited_urls = set()
        self.crawled_data = []
        self.driver = None
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
    def setup_driver(self):
        """Initialize Chrome driver with optimized options for speed"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--disable-features=VizDisplayCompositor")
        chrome_options.add_argument("--window-size=1280,720")
        chrome_options.add_argument("--aggressive-cache-discard")
        chrome_options.add_argument("--memory-pressure-off")
        
        # Optimize for speed while keeping JS enabled
        prefs = {
            "profile.managed_default_content_settings.images": 2,  # Block images
            "profile.default_content_setting_values.notifications": 2,
            "profile.managed_default_content_settings.stylesheets": 2,  # Block CSS
            "profile.managed_default_content_settings.cookies": 2,
            "profile.managed_default_content_settings.javascript": 1,  # Allow JS
            "profile.managed_default_content_settings.plugins": 2,
            "profile.managed_default_content_settings.popups": 2,
            "profile.managed_default_content_settings.geolocation": 2,
            "profile.managed_default_content_settings.media_stream": 2,
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        try:
            # Clear any cached drivers that might be corrupted
            import shutil
            cache_dir = os.path.expanduser("~/.wdm")
            if os.path.exists(cache_dir):
                try:
                    shutil.rmtree(cache_dir)
                    self.logger.info("Cleared webdriver-manager cache")
                except:
                    pass
            
            # Try webdriver-manager with fresh download
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.logger.info("Chrome driver initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize Chrome driver: {e}")
            try:
                # Fallback: try system Chrome driver (assumes ChromeDriver is in PATH)
                self.driver = webdriver.Chrome(options=chrome_options)
                self.logger.info("Chrome driver initialized with system driver")
            except Exception as e2:
                self.logger.error(f"System Chrome driver also failed: {e2}")
                raise Exception(
                    "Could not initialize Chrome driver. Please:\n"
                    "1. Ensure Google Chrome is installed\n"
                    "2. Download ChromeDriver from https://chromedriver.chromium.org/\n"
                    "3. Add ChromeDriver to your system PATH\n"
                    "4. Or try running without --headless mode"
                )
        
        self.driver.implicitly_wait(3)  # Reduced wait time
        self.driver.set_page_load_timeout(10)  # Set page load timeout
        
    def close_driver(self):
        """Close the browser driver"""
        if self.driver:
            self.driver.quit()
            
    def is_valid_url(self, url):
        """Check if URL belongs to the same domain"""
        try:
            parsed = urlparse(url)
            return parsed.netloc == self.domain or parsed.netloc == ""
        except:
            return False
            
    def wait_for_page_load(self):
        """Wait for page to load with minimal delay"""
        try:
            WebDriverWait(self.driver, 5).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            if self.delay > 0:
                time.sleep(self.delay)
        except TimeoutException:
            self.logger.warning("Page load timeout - continuing anyway")
            
    def handle_pagination(self):
        """Handle pagination buttons (next, previous, numbered pages)"""
        pagination_data = []
        
        # Common pagination selectors
        pagination_selectors = [
            "//a[contains(text(), 'Next') or contains(text(), 'next') or contains(text(), 'NEXT')]",
            "//button[contains(text(), 'Next') or contains(text(), 'next') or contains(text(), 'NEXT')]",
            "//a[contains(@class, 'next') or contains(@class, 'pagination-next')]",
            "//button[contains(@class, 'next') or contains(@class, 'pagination-next')]",
            "//a[contains(text(), 'Previous') or contains(text(), 'previous') or contains(text(), 'PREVIOUS')]",
            "//button[contains(text(), 'Previous') or contains(text(), 'previous') or contains(text(), 'PREVIOUS')]",
            "//a[contains(@class, 'prev') or contains(@class, 'pagination-prev')]",
            "//button[contains(@class, 'prev') or contains(@class, 'pagination-prev')]"
        ]
        
        for selector in pagination_selectors:
            try:
                elements = self.driver.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed() and element.is_enabled():
                        href = element.get_attribute('href') or element.get_attribute('onclick')
                        text = element.text.strip()
                        pagination_data.append({
                            'type': 'pagination',
                            'text': text,
                            'href': href,
                            'tag': element.tag_name,
                            'class': element.get_attribute('class')
                        })
            except:
                continue
                
        return pagination_data
        
    def handle_dynamic_content(self):
        """Handle dynamic content in ul/li format and interactive elements"""
        dynamic_content = []
        
        # Look for ul/li structures that might contain dynamic content
        try:
            ul_elements = self.driver.find_elements(By.TAG_NAME, "ul")
            for ul in ul_elements:
                li_elements = ul.find_elements(By.TAG_NAME, "li")
                if li_elements:
                    ul_data = {
                        'type': 'list_container',
                        'class': ul.get_attribute('class'),
                        'id': ul.get_attribute('id'),
                        'items': []
                    }
                    
                    for li in li_elements:
                        # Check for clickable elements within li
                        clickable_elements = li.find_elements(By.XPATH, ".//a | .//button")
                        li_data = {
                            'text': li.text.strip(),
                            'class': li.get_attribute('class'),
                            'clickable_elements': []
                        }
                        
                        for clickable in clickable_elements:
                            if clickable.is_displayed():
                                li_data['clickable_elements'].append({
                                    'tag': clickable.tag_name,
                                    'text': clickable.text.strip(),
                                    'href': clickable.get_attribute('href'),
                                    'class': clickable.get_attribute('class'),
                                    'onclick': clickable.get_attribute('onclick')
                                })
                        
                        ul_data['items'].append(li_data)
                    
                    dynamic_content.append(ul_data)
        except Exception as e:
            self.logger.error(f"Error handling dynamic content: {e}")
            
        return dynamic_content
        
    def detect_animations_and_interactions(self):
        """Detect elements that might trigger animations or load new content"""
        interactive_elements = []
        
        # Look for elements that might trigger content loading
        selectors = [
            "//button[contains(@class, 'load-more') or contains(text(), 'Load More')]",
            "//a[contains(@class, 'load-more') or contains(text(), 'Load More')]",
            "//button[contains(@class, 'show-more') or contains(text(), 'Show More')]",
            "//div[contains(@class, 'carousel') or contains(@class, 'slider')]",
            "//button[contains(@class, 'tab') or @role='tab']",
            "//a[contains(@class, 'tab') or @role='tab']"
        ]
        
        for selector in selectors:
            try:
                elements = self.driver.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed():
                        interactive_elements.append({
                            'type': 'interactive',
                            'tag': element.tag_name,
                            'text': element.text.strip(),
                            'class': element.get_attribute('class'),
                            'id': element.get_attribute('id'),
                            'href': element.get_attribute('href'),
                            'onclick': element.get_attribute('onclick')
                        })
            except:
                continue
                
        return interactive_elements
        
    def extract_all_links(self):
        """Extract all links from the current page"""
        links = []
        try:
            link_elements = self.driver.find_elements(By.TAG_NAME, "a")
            for link in link_elements:
                href = link.get_attribute('href')
                if href and self.is_valid_url(href):
                    absolute_url = urljoin(self.driver.current_url, href)
                    links.append({
                        'url': absolute_url,
                        'text': link.text.strip(),
                        'class': link.get_attribute('class')
                    })
        except Exception as e:
            self.logger.error(f"Error extracting links: {e}")
            
        return links
        
    def crawl_page(self, url, depth=0):
        """Crawl a single page and extract all relevant data"""
        if (depth > self.max_depth or 
            url in self.visited_urls or 
            len(self.crawled_data) >= self.max_pages):
            return
            
        self.visited_urls.add(url)
        self.logger.info(f"Crawling: {url} (depth: {depth}) - Page {len(self.crawled_data)+1}/{self.max_pages}")
        
        try:
            self.driver.get(url)
            self.wait_for_page_load()
            
            # Get page source for BeautifulSoup parsing
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # Extract page data
            page_data = {
                'url': url,
                'title': self.driver.title,
                'depth': depth,
                'meta_description': '',
                'headings': {},
                'links': self.extract_all_links(),
                'pagination': self.handle_pagination(),
                'dynamic_content': self.handle_dynamic_content(),
                'interactive_elements': self.detect_animations_and_interactions(),
                'forms': [],
                'images': []
            }
            
            # Extract meta description
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc:
                page_data['meta_description'] = meta_desc.get('content', '')
                
            # Extract headings
            for i in range(1, 7):
                headings = soup.find_all(f'h{i}')
                page_data['headings'][f'h{i}'] = [h.get_text().strip() for h in headings]
                
            # Extract forms
            forms = soup.find_all('form')
            for form in forms:
                form_data = {
                    'action': form.get('action', ''),
                    'method': form.get('method', 'get'),
                    'inputs': []
                }
                inputs = form.find_all(['input', 'select', 'textarea'])
                for inp in inputs:
                    form_data['inputs'].append({
                        'type': inp.get('type', ''),
                        'name': inp.get('name', ''),
                        'id': inp.get('id', ''),
                        'placeholder': inp.get('placeholder', '')
                    })
                page_data['forms'].append(form_data)
                
            # Extract images
            images = soup.find_all('img')
            for img in images:
                src = img.get('src')
                if src:
                    page_data['images'].append({
                        'src': urljoin(url, src),
                        'alt': img.get('alt', ''),
                        'title': img.get('title', '')
                    })
            
            self.crawled_data.append(page_data)
            
            # Recursively crawl linked pages
            for link_data in page_data['links']:
                link_url = link_data['url']
                if link_url not in self.visited_urls and self.is_valid_url(link_url):
                    self.crawl_page(link_url, depth + 1)
                    
        except Exception as e:
            self.logger.error(f"Error crawling {url}: {e}")
            
    def crawl(self):
        """Main crawling method"""
        self.setup_driver()
        try:
            self.crawl_page(self.base_url)
        finally:
            self.close_driver()
            
        return self.crawled_data
        
    def save_to_json(self, filename='crawled_data.json'):
        """Save crawled data to JSON file"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.crawled_data, f, indent=2, ensure_ascii=False)
        self.logger.info(f"Data saved to {filename}")
        
    def get_summary(self):
        """Get a summary of crawled data"""
        total_pages = len(self.crawled_data)
        total_links = sum(len(page['links']) for page in self.crawled_data)
        pages_with_pagination = sum(1 for page in self.crawled_data if page['pagination'])
        pages_with_dynamic_content = sum(1 for page in self.crawled_data if page['dynamic_content'])
        
        return {
            'total_pages_crawled': total_pages,
            'total_links_found': total_links,
            'pages_with_pagination': pages_with_pagination,
            'pages_with_dynamic_content': pages_with_dynamic_content,
            'unique_urls': list(self.visited_urls)
        }

if __name__ == "__main__":
    # Example usage
    base_url = input("Enter the base URL to crawl: ").strip()
    max_depth = int(input("Enter maximum crawl depth (default 2): ") or 2)
    
    crawler = WebCrawler(base_url, max_depth=max_depth)
    
    print("Starting crawl...")
    crawled_data = crawler.crawl()
    
    # Save to JSON
    crawler.save_to_json()
    
    # Print summary
    summary = crawler.get_summary()
    print("\nCrawl Summary:")
    print(json.dumps(summary, indent=2))