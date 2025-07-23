import json
import os
import re
import time
import logging
import requests
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import concurrent.futures
import threading
from pathlib import Path

class HTMLExtractor:
    def __init__(self, crawled_urls_file='crawled_urls.json', output_dir='extracted_html'):
        self.crawled_urls_file = crawled_urls_file
        self.output_dir = output_dir
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # Setup logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        
        # Thread lock for file operations
        self.lock = threading.Lock()
        
        # Create output directory
        Path(self.output_dir).mkdir(exist_ok=True)
        
    def load_urls(self):
        """Load URLs from crawled_urls.json"""
        try:
            with open(self.crawled_urls_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Filter out non-HTTP URLs (javascript, mailto, tel)
            urls = [url for url in data['unique_urls'] 
                   if url.startswith(('http://', 'https://'))]
            
            self.logger.info(f"Loaded {len(urls)} valid URLs from {self.crawled_urls_file}")
            return urls
            
        except Exception as e:
            self.logger.error(f"Error loading URLs: {e}")
            return []
    
    def create_page_identifier(self, url):
        """Create a clean identifier for the page"""
        parsed = urlparse(url)
        
        # Get the path and clean it
        path = parsed.path.strip('/')
        
        if not path or path == '':
            identifier = 'homepage'
        else:
            # Replace special characters and create readable name
            identifier = re.sub(r'[^\w\-_.]', '_', path)
            identifier = re.sub(r'_+', '_', identifier)  # Remove multiple underscores
            identifier = identifier.strip('_')
            
            # Remove .html extension for cleaner names
            if identifier.endswith('.html'):
                identifier = identifier[:-5]
        
        # Add query parameters if they exist
        if parsed.query:
            query_clean = re.sub(r'[^\w\-_=&]', '_', parsed.query)
            identifier += f"_query_{query_clean}"
        
        # Ensure identifier is not too long
        if len(identifier) > 100:
            identifier = identifier[:100]
        
        return identifier
    
    def extract_components(self, soup, page_dir):
        """Extract different components from HTML and save them"""
        components = {}
        
        try:
            # Extract navigation
            nav_elements = soup.find_all(['nav', 'div'], class_=re.compile(r'nav|menu|header', re.I))
            if nav_elements:
                components['navigation'] = [str(nav) for nav in nav_elements[:3]]  # Limit to 3
            
            # Extract main content
            main_content = soup.find(['main', 'div'], class_=re.compile(r'main|content|body', re.I))
            if main_content:
                components['main_content'] = str(main_content)
            
            # Extract articles/blog posts
            articles = soup.find_all(['article', 'div'], class_=re.compile(r'article|post|blog|story', re.I))
            if articles:
                components['articles'] = [str(article) for article in articles[:5]]  # Limit to 5
            
            # Extract cards/tiles
            cards = soup.find_all(['div', 'section'], class_=re.compile(r'card|tile|item|box', re.I))
            if cards:
                components['cards'] = [str(card) for card in cards[:10]]  # Limit to 10
            
            # Extract forms
            forms = soup.find_all('form')
            if forms:
                components['forms'] = [str(form) for form in forms]
            
            # Extract tables
            tables = soup.find_all('table')
            if tables:
                components['tables'] = [str(table) for table in tables]
            
            # Extract lists
            lists = soup.find_all(['ul', 'ol'], class_=re.compile(r'list|menu', re.I))
            if lists:
                components['lists'] = [str(lst) for lst in lists[:5]]  # Limit to 5
            
            # Extract footer
            footer = soup.find(['footer', 'div'], class_=re.compile(r'footer', re.I))
            if footer:
                components['footer'] = str(footer)
            
            # Extract metadata
            meta_data = {
                'title': soup.title.string if soup.title else '',
                'meta_description': '',
                'meta_keywords': '',
                'h1_tags': [h1.get_text().strip() for h1 in soup.find_all('h1')],
                'h2_tags': [h2.get_text().strip() for h2 in soup.find_all('h2')[:5]],  # Limit to 5
                'images': [img.get('src', '') for img in soup.find_all('img')[:10]],  # Limit to 10
                'links_count': len(soup.find_all('a')),
            }
            
            # Get meta description and keywords
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc:
                meta_data['meta_description'] = meta_desc.get('content', '')
            
            meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
            if meta_keywords:
                meta_data['meta_keywords'] = meta_keywords.get('content', '')
            
            components['metadata'] = meta_data
            
            # Save components to separate files
            self.save_components(components, page_dir)
            
        except Exception as e:
            self.logger.error(f"Error extracting components: {e}")
    
    def save_components(self, components, page_dir):
        """Save extracted components to separate files"""
        try:
            for component_type, content in components.items():
                if not content:
                    continue
                
                component_file = page_dir / f"{component_type}.json"
                
                if component_type == 'metadata':
                    # Save metadata as JSON
                    with open(component_file, 'w', encoding='utf-8') as f:
                        json.dump(content, f, indent=2, ensure_ascii=False)
                else:
                    # Save HTML components
                    component_data = {
                        'type': component_type,
                        'count': len(content) if isinstance(content, list) else 1,
                        'content': content
                    }
                    
                    with open(component_file, 'w', encoding='utf-8') as f:
                        json.dump(component_data, f, indent=2, ensure_ascii=False)
                        
        except Exception as e:
            self.logger.error(f"Error saving components: {e}")
    
    def extract_single_url(self, url):
        """Extract HTML and components from a single URL"""
        try:
            # Create page identifier and directory
            page_id = self.create_page_identifier(url)
            page_dir = Path(self.output_dir) / page_id
            page_dir.mkdir(exist_ok=True)
            
            # Check if already processed
            html_file = page_dir / 'page.html'
            if html_file.exists():
                self.logger.info(f"⏭️  Skipping {url} - already processed")
                return True
            
            # Fetch the page
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Save raw HTML
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(soup.prettify())
            
            # Save URL info
            url_info = {
                'original_url': url,
                'page_identifier': page_id,
                'status_code': response.status_code,
                'content_type': response.headers.get('content-type', ''),
                'content_length': len(response.content),
                'extraction_timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            
            with open(page_dir / 'url_info.json', 'w', encoding='utf-8') as f:
                json.dump(url_info, f, indent=2, ensure_ascii=False)
            
            # Extract components
            self.extract_components(soup, page_dir)
            
            with self.lock:
                self.logger.info(f"✅ Extracted: {url} -> {page_id}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error extracting {url}: {e}")
            return False
    
    def extract_all(self, max_workers=5):
        """Extract HTML and components from all URLs"""
        urls = self.load_urls()
        if not urls:
            self.logger.error("No URLs to process")
            return
        
        self.logger.info(f"🚀 Starting extraction of {len(urls)} URLs with {max_workers} workers")
        
        success_count = 0
        failed_count = 0
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_url = {executor.submit(self.extract_single_url, url): url for url in urls}
            
            # Process completed tasks
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    success = future.result()
                    if success:
                        success_count += 1
                    else:
                        failed_count += 1
                        
                    # Progress report every 10 completions
                    if (success_count + failed_count) % 10 == 0:
                        self.logger.info(f"📊 Progress: {success_count} success, {failed_count} failed, {len(urls) - success_count - failed_count} remaining")
                        
                except Exception as e:
                    failed_count += 1
                    self.logger.error(f"❌ Task failed for {url}: {e}")
        
        # Final summary
        self.logger.info(f"🎉 Extraction complete!")
        self.logger.info(f"✅ Successful: {success_count}")
        self.logger.info(f"❌ Failed: {failed_count}")
        self.logger.info(f"📁 Output directory: {self.output_dir}")
        
        # Create summary file
        summary = {
            'total_urls': len(urls),
            'successful_extractions': success_count,
            'failed_extractions': failed_count,
            'output_directory': self.output_dir,
            'extraction_timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        with open(Path(self.output_dir) / 'extraction_summary.json', 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    print("🔧 HTML Extractor - Component Analysis Tool")
    print("=" * 60)
    
    # Configuration
    crawled_file = input("Enter crawled URLs file (default: crawled_urls.json): ").strip() or "crawled_urls.json"
    output_dir = input("Enter output directory (default: extracted_html): ").strip() or "extracted_html"
    max_workers = int(input("Enter max concurrent workers (default: 5): ") or 5)
    
    # Create extractor
    extractor = HTMLExtractor(crawled_urls_file=crawled_file, output_dir=output_dir)
    
    print(f"\n🔍 Starting HTML extraction and component analysis")
    print(f"📂 Input file: {crawled_file}")
    print(f"📁 Output directory: {output_dir}")
    print(f"⚡ Workers: {max_workers}")
    print("=" * 60)
    
    # Start extraction
    extractor.extract_all(max_workers=max_workers)
    
    print(f"\n📁 Check the '{output_dir}' folder for extracted content!")
    print("Each page has its own folder with:")
    print("  • page.html - Raw HTML content")
    print("  • url_info.json - Page metadata")
    print("  • Component files (navigation.json, articles.json, etc.)")