import json
import os
import re
import time
import logging
import requests
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup, Comment
import concurrent.futures
import threading
from pathlib import Path
from collections import Counter, defaultdict
import hashlib

class AdvancedComponentAnalyzer:
    def __init__(self, crawled_urls_file='crawled_urls.json', output_dir='advanced_extracted_html'):
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
        
        # Component analysis strategies
        self.analysis_strategies = {
            'semantic': self.semantic_analysis,
            'structural': self.structural_analysis,
            'content_type': self.content_type_analysis,
            'interactive': self.interactive_elements_analysis,
            'layout': self.layout_analysis,
            'seo': self.seo_analysis,
            'accessibility': self.accessibility_analysis,
            'performance': self.performance_analysis
        }
        
    def load_urls(self):
        """Load URLs from crawled_urls.json"""
        try:
            with open(self.crawled_urls_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Filter out non-HTTP URLs (javascript, mailto, tel)
            urls = [url for url in data['unique_urls'] 
                   if url.startswith(('http://', 'https://'))]
            
            self.logger.info(f"Loaded {len(urls)} valid URLs from {self.crawled_urls_file}")
            return urls, data.get('dynamic_urls', [])
            
        except Exception as e:
            self.logger.error(f"Error loading URLs: {e}")
            return [], []
    
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
    
    def semantic_analysis(self, soup, url):
        """Analyze semantic HTML elements and structure"""
        semantic_data = {
            'html5_semantic_tags': {},
            'heading_structure': {},
            'content_sections': {},
            'microdata': {},
            'schema_org': {},
            'open_graph': {},
            'twitter_cards': {}
        }
        
        # HTML5 semantic tags
        semantic_tags = ['header', 'nav', 'main', 'section', 'article', 'aside', 'footer', 'figure', 'figcaption']
        for tag in semantic_tags:
            elements = soup.find_all(tag)
            semantic_data['html5_semantic_tags'][tag] = {
                'count': len(elements),
                'content': [{'text': elem.get_text()[:200], 'classes': elem.get('class', [])} for elem in elements[:3]]
            }
        
        # Heading structure analysis
        headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        heading_hierarchy = []
        for heading in headings:
            heading_hierarchy.append({
                'level': heading.name,
                'text': heading.get_text().strip(),
                'id': heading.get('id', ''),
                'classes': heading.get('class', [])
            })
        semantic_data['heading_structure'] = {
            'hierarchy': heading_hierarchy,
            'h1_count': len(soup.find_all('h1')),
            'total_headings': len(headings)
        }
        
        # Content sections
        sections = soup.find_all('section')
        articles = soup.find_all('article')
        semantic_data['content_sections'] = {
            'sections': [{'id': s.get('id', ''), 'classes': s.get('class', []), 'text_length': len(s.get_text())} for s in sections],
            'articles': [{'id': a.get('id', ''), 'classes': a.get('class', []), 'text_length': len(a.get_text())} for a in articles]
        }
        
        # Microdata and Schema.org
        microdata_items = soup.find_all(attrs={'itemscope': True})
        for item in microdata_items:
            item_type = item.get('itemtype', 'unknown')
            if item_type not in semantic_data['microdata']:
                semantic_data['microdata'][item_type] = []
            
            properties = {}
            for prop in item.find_all(attrs={'itemprop': True}):
                prop_name = prop.get('itemprop')
                prop_value = prop.get_text().strip() or prop.get('content', '')
                properties[prop_name] = prop_value
            
            semantic_data['microdata'][item_type].append(properties)
        
        # Open Graph tags
        og_tags = soup.find_all('meta', property=re.compile(r'^og:'))
        for tag in og_tags:
            prop = tag.get('property', '')
            content = tag.get('content', '')
            semantic_data['open_graph'][prop] = content
        
        # Twitter Card tags
        twitter_tags = soup.find_all('meta', attrs={'name': re.compile(r'^twitter:')})
        for tag in twitter_tags:
            name = tag.get('name', '')
            content = tag.get('content', '')
            semantic_data['twitter_cards'][name] = content
        
        return semantic_data
    
    def structural_analysis(self, soup, url):
        """Analyze page structure and layout patterns"""
        structural_data = {
            'dom_depth': 0,
            'total_elements': 0,
            'element_distribution': {},
            'class_patterns': {},
            'id_patterns': {},
            'nesting_patterns': {},
            'container_analysis': {}
        }
        
        # Calculate DOM depth
        def calculate_depth(element, current_depth=0):
            max_depth = current_depth
            for child in element.find_all(recursive=False):
                child_depth = calculate_depth(child, current_depth + 1)
                max_depth = max(max_depth, child_depth)
            return max_depth
        
        structural_data['dom_depth'] = calculate_depth(soup.body if soup.body else soup)
        
        # Element distribution
        all_elements = soup.find_all()
        structural_data['total_elements'] = len(all_elements)
        
        element_counts = Counter(elem.name for elem in all_elements)
        structural_data['element_distribution'] = dict(element_counts.most_common(20))
        
        # Class patterns analysis
        all_classes = []
        for elem in all_elements:
            classes = elem.get('class', [])
            all_classes.extend(classes)
        
        class_counts = Counter(all_classes)
        structural_data['class_patterns'] = {
            'most_common': dict(class_counts.most_common(20)),
            'total_unique_classes': len(class_counts),
            'framework_indicators': self.detect_frameworks(all_classes)
        }
        
        # ID patterns
        all_ids = [elem.get('id') for elem in all_elements if elem.get('id')]
        structural_data['id_patterns'] = {
            'total_ids': len(all_ids),
            'common_prefixes': self.analyze_id_patterns(all_ids)
        }
        
        # Container analysis
        containers = soup.find_all(['div', 'section', 'article', 'main', 'aside'])
        container_analysis = {
            'total_containers': len(containers),
            'deeply_nested': 0,
            'layout_containers': []
        }
        
        for container in containers:
            depth = len(list(container.parents))
            if depth > 10:
                container_analysis['deeply_nested'] += 1
            
            classes = container.get('class', [])
            if any(keyword in ' '.join(classes).lower() for keyword in ['container', 'wrapper', 'layout', 'grid', 'flex']):
                container_analysis['layout_containers'].append({
                    'tag': container.name,
                    'classes': classes,
                    'children_count': len(container.find_all(recursive=False))
                })
        
        structural_data['container_analysis'] = container_analysis
        
        return structural_data
    
    def content_type_analysis(self, soup, url):
        """Analyze different types of content on the page"""
        content_data = {
            'text_content': {},
            'media_content': {},
            'interactive_content': {},
            'data_content': {},
            'navigation_content': {}
        }
        
        # Text content analysis
        paragraphs = soup.find_all('p')
        headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        lists = soup.find_all(['ul', 'ol'])
        
        content_data['text_content'] = {
            'paragraphs': {
                'count': len(paragraphs),
                'avg_length': sum(len(p.get_text()) for p in paragraphs) / len(paragraphs) if paragraphs else 0,
                'total_words': sum(len(p.get_text().split()) for p in paragraphs)
            },
            'headings': {
                'count': len(headings),
                'distribution': Counter(h.name for h in headings)
            },
            'lists': {
                'count': len(lists),
                'types': Counter(l.name for l in lists),
                'total_items': sum(len(l.find_all('li')) for l in lists)
            }
        }
        
        # Media content analysis
        images = soup.find_all('img')
        videos = soup.find_all(['video', 'iframe'])
        audio = soup.find_all('audio')
        
        content_data['media_content'] = {
            'images': {
                'count': len(images),
                'with_alt': len([img for img in images if img.get('alt')]),
                'lazy_loaded': len([img for img in images if 'lazy' in str(img.get('loading', '')) or 'lazy' in ' '.join(img.get('class', []))]),
                'formats': Counter(img.get('src', '').split('.')[-1].lower() for img in images if img.get('src') and '.' in img.get('src'))
            },
            'videos': {
                'count': len(videos),
                'embedded': len([v for v in videos if v.name == 'iframe']),
                'native': len([v for v in videos if v.name == 'video'])
            },
            'audio': {
                'count': len(audio)
            }
        }
        
        # Interactive content analysis
        forms = soup.find_all('form')
        buttons = soup.find_all(['button', 'input'])
        links = soup.find_all('a')
        
        content_data['interactive_content'] = {
            'forms': {
                'count': len(forms),
                'methods': Counter(form.get('method', 'get').lower() for form in forms),
                'total_inputs': sum(len(form.find_all(['input', 'textarea', 'select'])) for form in forms)
            },
            'buttons': {
                'count': len(buttons),
                'types': Counter(btn.get('type', 'button') for btn in buttons if btn.name == 'input')
            },
            'links': {
                'count': len(links),
                'external': len([link for link in links if self.is_external_link(link.get('href', ''), url)]),
                'internal': len([link for link in links if not self.is_external_link(link.get('href', ''), url) and link.get('href')])
            }
        }
        
        # Data content analysis
        tables = soup.find_all('table')
        lists_data = soup.find_all(['dl', 'ul', 'ol'])
        
        content_data['data_content'] = {
            'tables': {
                'count': len(tables),
                'with_headers': len([table for table in tables if table.find('th')]),
                'total_cells': sum(len(table.find_all(['td', 'th'])) for table in tables)
            },
            'structured_lists': {
                'count': len(lists_data),
                'definition_lists': len([l for l in lists_data if l.name == 'dl'])
            }
        }
        
        # Navigation content analysis
        nav_elements = soup.find_all('nav')
        breadcrumbs = soup.find_all(attrs={'class': re.compile(r'breadcrumb', re.I)})
        menus = soup.find_all(['ul', 'ol'], class_=re.compile(r'menu|nav', re.I))
        
        content_data['navigation_content'] = {
            'nav_elements': len(nav_elements),
            'breadcrumbs': len(breadcrumbs),
            'menu_lists': len(menus),
            'skip_links': len(soup.find_all('a', href=re.compile(r'^#')))
        }
        
        return content_data
    
    def interactive_elements_analysis(self, soup, url):
        """Analyze interactive elements and user interface components"""
        interactive_data = {
            'form_elements': {},
            'navigation_elements': {},
            'media_controls': {},
            'dynamic_elements': {},
            'accessibility_features': {}
        }
        
        # Form elements analysis
        forms = soup.find_all('form')
        form_analysis = []
        for form in forms:
            inputs = form.find_all(['input', 'textarea', 'select'])
            form_analysis.append({
                'action': form.get('action', ''),
                'method': form.get('method', 'get'),
                'input_count': len(inputs),
                'input_types': Counter(inp.get('type', 'text') for inp in inputs if inp.name == 'input'),
                'has_validation': bool(form.find_all(attrs={'required': True})),
                'has_labels': len(form.find_all('label'))
            })
        
        interactive_data['form_elements'] = {
            'forms': form_analysis,
            'total_forms': len(forms)
        }
        
        # Navigation elements
        nav_elements = soup.find_all(['nav', 'a'])
        nav_links = [a for a in nav_elements if a.name == 'a' and a.get('href')]
        
        interactive_data['navigation_elements'] = {
            'nav_containers': len([n for n in nav_elements if n.name == 'nav']),
            'total_links': len(nav_links),
            'anchor_links': len([a for a in nav_links if a.get('href', '').startswith('#')]),
            'download_links': len([a for a in nav_links if a.get('download')]),
            'external_links': len([a for a in nav_links if self.is_external_link(a.get('href', ''), url)])
        }
        
        # Media controls
        media_elements = soup.find_all(['video', 'audio'])
        interactive_data['media_controls'] = {
            'controllable_media': len([m for m in media_elements if m.get('controls')]),
            'autoplay_media': len([m for m in media_elements if m.get('autoplay')]),
            'muted_media': len([m for m in media_elements if m.get('muted')])
        }
        
        # Dynamic elements (JavaScript-related)
        dynamic_elements = soup.find_all(attrs={'onclick': True})
        data_attributes = soup.find_all(attrs=lambda x: x and any(attr.startswith('data-') for attr in x))
        
        interactive_data['dynamic_elements'] = {
            'onclick_elements': len(dynamic_elements),
            'data_attributes': len(data_attributes),
            'common_data_attrs': self.analyze_data_attributes(data_attributes)
        }
        
        # Accessibility features
        aria_elements = soup.find_all(attrs=lambda x: x and any(attr.startswith('aria-') for attr in x))
        role_elements = soup.find_all(attrs={'role': True})
        
        interactive_data['accessibility_features'] = {
            'aria_elements': len(aria_elements),
            'role_elements': len(role_elements),
            'alt_texts': len(soup.find_all('img', alt=True)),
            'skip_links': len(soup.find_all('a', href=re.compile(r'^#skip|^#main|^#content')))
        }
        
        return interactive_data
    
    def layout_analysis(self, soup, url):
        """Analyze layout patterns and CSS framework usage"""
        layout_data = {
            'css_frameworks': {},
            'layout_patterns': {},
            'responsive_indicators': {},
            'grid_systems': {}
        }
        
        # Detect CSS frameworks
        all_classes = []
        for elem in soup.find_all():
            all_classes.extend(elem.get('class', []))
        
        framework_indicators = {
            'bootstrap': ['container', 'row', 'col-', 'btn-', 'navbar', 'card'],
            'tailwind': ['flex', 'grid', 'p-', 'm-', 'text-', 'bg-'],
            'bulma': ['column', 'columns', 'section', 'hero', 'navbar'],
            'foundation': ['grid-x', 'cell', 'callout', 'button'],
            'materialize': ['collection', 'waves-effect', 'material-icons'],
            'semantic_ui': ['ui', 'segment', 'container', 'grid']
        }
        
        detected_frameworks = {}
        for framework, indicators in framework_indicators.items():
            matches = sum(1 for indicator in indicators if any(indicator in cls for cls in all_classes))
            if matches > 0:
                detected_frameworks[framework] = {
                    'matches': matches,
                    'confidence': min(matches / len(indicators), 1.0)
                }
        
        layout_data['css_frameworks'] = detected_frameworks
        
        # Layout patterns
        containers = soup.find_all(class_=re.compile(r'container|wrapper|main|content'))
        grids = soup.find_all(class_=re.compile(r'grid|row|flex'))
        sidebars = soup.find_all(class_=re.compile(r'sidebar|aside|secondary'))
        
        layout_data['layout_patterns'] = {
            'containers': len(containers),
            'grid_elements': len(grids),
            'sidebars': len(sidebars),
            'header_footer': {
                'headers': len(soup.find_all(['header', 'div'], class_=re.compile(r'header'))),
                'footers': len(soup.find_all(['footer', 'div'], class_=re.compile(r'footer')))
            }
        }
        
        # Responsive indicators
        viewport_meta = soup.find('meta', attrs={'name': 'viewport'})
        media_queries = len(re.findall(r'@media', str(soup)))
        responsive_classes = [cls for cls in all_classes if any(indicator in cls for indicator in ['sm-', 'md-', 'lg-', 'xl-', 'mobile', 'tablet', 'desktop'])]
        
        layout_data['responsive_indicators'] = {
            'viewport_meta': bool(viewport_meta),
            'viewport_content': viewport_meta.get('content', '') if viewport_meta else '',
            'media_queries_count': media_queries,
            'responsive_classes': len(responsive_classes)
        }
        
        return layout_data
    
    def seo_analysis(self, soup, url):
        """Analyze SEO-related elements"""
        seo_data = {
            'meta_tags': {},
            'heading_structure': {},
            'content_optimization': {},
            'technical_seo': {}
        }
        
        # Meta tags analysis
        title = soup.find('title')
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
        canonical = soup.find('link', attrs={'rel': 'canonical'})
        
        seo_data['meta_tags'] = {
            'title': {
                'exists': bool(title),
                'content': title.get_text() if title else '',
                'length': len(title.get_text()) if title else 0
            },
            'description': {
                'exists': bool(meta_desc),
                'content': meta_desc.get('content', '') if meta_desc else '',
                'length': len(meta_desc.get('content', '')) if meta_desc else 0
            },
            'keywords': {
                'exists': bool(meta_keywords),
                'content': meta_keywords.get('content', '') if meta_keywords else ''
            },
            'canonical': {
                'exists': bool(canonical),
                'href': canonical.get('href', '') if canonical else ''
            }
        }
        
        # Heading structure for SEO
        headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        h1_tags = soup.find_all('h1')
        
        seo_data['heading_structure'] = {
            'h1_count': len(h1_tags),
            'h1_content': [h1.get_text().strip() for h1 in h1_tags],
            'heading_hierarchy': [h.name for h in headings],
            'total_headings': len(headings)
        }
        
        # Content optimization
        images = soup.find_all('img')
        links = soup.find_all('a')
        
        seo_data['content_optimization'] = {
            'images_with_alt': len([img for img in images if img.get('alt')]),
            'images_without_alt': len([img for img in images if not img.get('alt')]),
            'internal_links': len([a for a in links if a.get('href') and not self.is_external_link(a.get('href'), url)]),
            'external_links': len([a for a in links if a.get('href') and self.is_external_link(a.get('href'), url)]),
            'nofollow_links': len([a for a in links if 'nofollow' in a.get('rel', [])])
        }
        
        # Technical SEO
        structured_data = soup.find_all(attrs={'itemscope': True})
        json_ld = soup.find_all('script', type='application/ld+json')
        
        seo_data['technical_seo'] = {
            'structured_data_count': len(structured_data),
            'json_ld_count': len(json_ld),
            'robots_meta': bool(soup.find('meta', attrs={'name': 'robots'})),
            'lang_attribute': soup.html.get('lang', '') if soup.html else ''
        }
        
        return seo_data
    
    def accessibility_analysis(self, soup, url):
        """Analyze accessibility features"""
        accessibility_data = {
            'aria_attributes': {},
            'semantic_structure': {},
            'keyboard_navigation': {},
            'screen_reader_support': {}
        }
        
        # ARIA attributes
        aria_elements = soup.find_all(attrs=lambda x: x and any(attr.startswith('aria-') for attr in x))
        role_elements = soup.find_all(attrs={'role': True})
        
        accessibility_data['aria_attributes'] = {
            'total_aria_elements': len(aria_elements),
            'role_elements': len(role_elements),
            'common_roles': Counter(elem.get('role') for elem in role_elements),
            'aria_labels': len(soup.find_all(attrs={'aria-label': True})),
            'aria_describedby': len(soup.find_all(attrs={'aria-describedby': True}))
        }
        
        # Semantic structure
        landmarks = soup.find_all(['header', 'nav', 'main', 'section', 'article', 'aside', 'footer'])
        headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        
        accessibility_data['semantic_structure'] = {
            'landmark_elements': len(landmarks),
            'landmark_types': Counter(elem.name for elem in landmarks),
            'heading_levels': Counter(h.name for h in headings),
            'skip_links': len(soup.find_all('a', href=re.compile(r'^#skip|^#main|^#content')))
        }
        
        # Keyboard navigation
        focusable_elements = soup.find_all(['a', 'button', 'input', 'textarea', 'select'])
        tabindex_elements = soup.find_all(attrs={'tabindex': True})
        
        accessibility_data['keyboard_navigation'] = {
            'focusable_elements': len(focusable_elements),
            'tabindex_elements': len(tabindex_elements),
            'negative_tabindex': len([elem for elem in tabindex_elements if int(elem.get('tabindex', 0)) < 0])
        }
        
        # Screen reader support
        images = soup.find_all('img')
        form_labels = soup.find_all('label')
        form_inputs = soup.find_all(['input', 'textarea', 'select'])
        
        accessibility_data['screen_reader_support'] = {
            'images_with_alt': len([img for img in images if img.get('alt')]),
            'decorative_images': len([img for img in images if img.get('alt') == '']),
            'form_labels': len(form_labels),
            'form_inputs': len(form_inputs),
            'label_input_ratio': len(form_labels) / len(form_inputs) if form_inputs else 0
        }
        
        return accessibility_data
    
    def performance_analysis(self, soup, url):
        """Analyze performance-related aspects"""
        performance_data = {
            'resource_hints': {},
            'lazy_loading': {},
            'optimization_indicators': {},
            'third_party_resources': {}
        }
        
        # Resource hints
        preload_links = soup.find_all('link', rel='preload')
        prefetch_links = soup.find_all('link', rel='prefetch')
        preconnect_links = soup.find_all('link', rel='preconnect')
        dns_prefetch_links = soup.find_all('link', rel='dns-prefetch')
        
        performance_data['resource_hints'] = {
            'preload': len(preload_links),
            'prefetch': len(prefetch_links),
            'preconnect': len(preconnect_links),
            'dns_prefetch': len(dns_prefetch_links)
        }
        
        # Lazy loading
        lazy_images = soup.find_all('img', loading='lazy')
        lazy_class_images = soup.find_all('img', class_=re.compile(r'lazy'))
        
        performance_data['lazy_loading'] = {
            'native_lazy_images': len(lazy_images),
            'class_based_lazy': len(lazy_class_images),
            'total_images': len(soup.find_all('img'))
        }
        
        # Optimization indicators
        minified_scripts = soup.find_all('script', src=re.compile(r'\.min\.js'))
        minified_styles = soup.find_all('link', href=re.compile(r'\.min\.css'))
        inline_scripts = soup.find_all('script', src=False)
        inline_styles = soup.find_all('style')
        
        performance_data['optimization_indicators'] = {
            'minified_scripts': len(minified_scripts),
            'minified_styles': len(minified_styles),
            'inline_scripts': len(inline_scripts),
            'inline_styles': len(inline_styles),
            'total_scripts': len(soup.find_all('script')),
            'total_stylesheets': len(soup.find_all('link', rel='stylesheet'))
        }
        
        # Third-party resources
        external_scripts = []
        external_styles = []
        
        for script in soup.find_all('script', src=True):
            src = script.get('src', '')
            if self.is_external_link(src, url):
                external_scripts.append(src)
        
        for link in soup.find_all('link', rel='stylesheet'):
            href = link.get('href', '')
            if self.is_external_link(href, url):
                external_styles.append(href)
        
        performance_data['third_party_resources'] = {
            'external_scripts': len(external_scripts),
            'external_styles': len(external_styles),
            'common_domains': Counter(urlparse(url).netloc for url in external_scripts + external_styles)
        }
        
        return performance_data
    
    def detect_frameworks(self, classes):
        """Detect CSS/JS frameworks from class names"""
        frameworks = {
            'bootstrap': ['container', 'row', 'col-', 'btn-', 'navbar'],
            'tailwind': ['flex', 'grid', 'p-', 'm-', 'text-'],
            'bulma': ['column', 'columns', 'section', 'hero'],
            'foundation': ['grid-x', 'cell', 'callout'],
            'materialize': ['collection', 'waves-effect'],
            'semantic_ui': ['ui', 'segment', 'container']
        }
        
        detected = {}
        for framework, indicators in frameworks.items():
            matches = sum(1 for indicator in indicators if any(indicator in cls for cls in classes))
            if matches > 0:
                detected[framework] = matches
        
        return detected
    
    def analyze_id_patterns(self, ids):
        """Analyze patterns in ID attributes"""
        if not ids:
            return {}
        
        prefixes = Counter()
        for id_val in ids:
            if '-' in id_val:
                prefix = id_val.split('-')[0]
                prefixes[prefix] += 1
            elif '_' in id_val:
                prefix = id_val.split('_')[0]
                prefixes[prefix] += 1
        
        return dict(prefixes.most_common(10))
    
    def analyze_data_attributes(self, elements):
        """Analyze data-* attributes"""
        data_attrs = []
        for elem in elements:
            for attr in elem.attrs:
                if attr.startswith('data-'):
                    data_attrs.append(attr)
        
        return dict(Counter(data_attrs).most_common(10))
    
    def is_external_link(self, href, base_url):
        """Check if a link is external"""
        if not href:
            return False
        
        if href.startswith(('http://', 'https://')):
            return urlparse(href).netloc != urlparse(base_url).netloc
        
        return False 
   
    def extract_and_save_html_components(self, soup, page_dir, url):
        """Extract and save HTML components as separate HTML files"""
        try:
            # Create components directory
            components_dir = page_dir / 'components'
            components_dir.mkdir(exist_ok=True)
            
            # Component extraction strategies
            component_extractions = {
                'headers': self.extract_header_components,
                'navigation': self.extract_navigation_components,
                'main_content': self.extract_main_content_components,
                'articles': self.extract_article_components,
                'cards': self.extract_card_components,
                'forms': self.extract_form_components,
                'tables': self.extract_table_components,
                'lists': self.extract_list_components,
                'media': self.extract_media_components,
                'footers': self.extract_footer_components,
                'sidebars': self.extract_sidebar_components,
                'modals': self.extract_modal_components,
                'buttons': self.extract_button_components,
                'breadcrumbs': self.extract_breadcrumb_components
            }
            
            # Extract each component type
            for component_type, extraction_func in component_extractions.items():
                try:
                    components = extraction_func(soup, url)
                    if components:
                        self.save_component_html(components, component_type, components_dir)
                except Exception as e:
                    self.logger.debug(f"Error extracting {component_type}: {e}")
            
            # Create component index
            self.create_component_index(components_dir, page_dir)
            
        except Exception as e:
            self.logger.error(f"Error in HTML component extraction: {e}")
    
    def extract_header_components(self, soup, url):
        """Extract header components"""
        headers = soup.find_all(['header', 'div'], class_=re.compile(r'header|top-bar|navbar', re.I))
        components = []
        
        for i, header in enumerate(headers[:5]):  # Limit to 5 headers
            components.append({
                'id': f'header_{i+1}',
                'html': str(header),
                'classes': header.get('class', []),
                'tag': header.name,
                'text_content': header.get_text()[:200]
            })
        
        return components
    
    def extract_navigation_components(self, soup, url):
        """Extract navigation components"""
        navs = soup.find_all(['nav', 'ul', 'ol'], class_=re.compile(r'nav|menu|navigation', re.I))
        components = []
        
        for i, nav in enumerate(navs[:10]):  # Limit to 10 navigation elements
            components.append({
                'id': f'navigation_{i+1}',
                'html': str(nav),
                'classes': nav.get('class', []),
                'tag': nav.name,
                'links_count': len(nav.find_all('a')),
                'text_content': nav.get_text()[:200]
            })
        
        return components
    
    def extract_main_content_components(self, soup, url):
        """Extract main content components"""
        main_elements = soup.find_all(['main', 'div'], class_=re.compile(r'main|content|body', re.I))
        components = []
        
        for i, main in enumerate(main_elements[:3]):  # Limit to 3 main content areas
            components.append({
                'id': f'main_content_{i+1}',
                'html': str(main),
                'classes': main.get('class', []),
                'tag': main.name,
                'text_length': len(main.get_text()),
                'text_content': main.get_text()[:500]
            })
        
        return components
    
    def extract_article_components(self, soup, url):
        """Extract article components"""
        articles = soup.find_all(['article', 'div'], class_=re.compile(r'article|post|blog|story|news', re.I))
        components = []
        
        for i, article in enumerate(articles[:10]):  # Limit to 10 articles
            components.append({
                'id': f'article_{i+1}',
                'html': str(article),
                'classes': article.get('class', []),
                'tag': article.name,
                'headings': len(article.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])),
                'images': len(article.find_all('img')),
                'text_content': article.get_text()[:300]
            })
        
        return components
    
    def extract_card_components(self, soup, url):
        """Extract card components"""
        cards = soup.find_all(['div', 'section'], class_=re.compile(r'card|tile|item|box|panel', re.I))
        components = []
        
        for i, card in enumerate(cards[:15]):  # Limit to 15 cards
            components.append({
                'id': f'card_{i+1}',
                'html': str(card),
                'classes': card.get('class', []),
                'tag': card.name,
                'links': len(card.find_all('a')),
                'images': len(card.find_all('img')),
                'text_content': card.get_text()[:200]
            })
        
        return components
    
    def extract_form_components(self, soup, url):
        """Extract form components"""
        forms = soup.find_all('form')
        components = []
        
        for i, form in enumerate(forms):
            components.append({
                'id': f'form_{i+1}',
                'html': str(form),
                'classes': form.get('class', []),
                'action': form.get('action', ''),
                'method': form.get('method', 'get'),
                'inputs': len(form.find_all(['input', 'textarea', 'select'])),
                'text_content': form.get_text()[:200]
            })
        
        return components
    
    def extract_table_components(self, soup, url):
        """Extract table components"""
        tables = soup.find_all('table')
        components = []
        
        for i, table in enumerate(tables):
            components.append({
                'id': f'table_{i+1}',
                'html': str(table),
                'classes': table.get('class', []),
                'rows': len(table.find_all('tr')),
                'headers': len(table.find_all('th')),
                'cells': len(table.find_all(['td', 'th'])),
                'text_content': table.get_text()[:300]
            })
        
        return components
    
    def extract_list_components(self, soup, url):
        """Extract list components"""
        lists = soup.find_all(['ul', 'ol', 'dl'])
        components = []
        
        for i, lst in enumerate(lists[:10]):  # Limit to 10 lists
            components.append({
                'id': f'list_{i+1}',
                'html': str(lst),
                'classes': lst.get('class', []),
                'tag': lst.name,
                'items': len(lst.find_all('li')) if lst.name in ['ul', 'ol'] else len(lst.find_all('dt')),
                'text_content': lst.get_text()[:200]
            })
        
        return components
    
    def extract_media_components(self, soup, url):
        """Extract media components"""
        media_elements = soup.find_all(['img', 'video', 'audio', 'iframe', 'figure'])
        components = []
        
        for i, media in enumerate(media_elements[:10]):  # Limit to 10 media elements
            components.append({
                'id': f'media_{i+1}',
                'html': str(media),
                'classes': media.get('class', []),
                'tag': media.name,
                'src': media.get('src', ''),
                'alt': media.get('alt', ''),
                'text_content': media.get_text()[:100] if media.get_text() else ''
            })
        
        return components
    
    def extract_footer_components(self, soup, url):
        """Extract footer components"""
        footers = soup.find_all(['footer', 'div'], class_=re.compile(r'footer|bottom', re.I))
        components = []
        
        for i, footer in enumerate(footers[:3]):  # Limit to 3 footers
            components.append({
                'id': f'footer_{i+1}',
                'html': str(footer),
                'classes': footer.get('class', []),
                'tag': footer.name,
                'links': len(footer.find_all('a')),
                'text_content': footer.get_text()[:300]
            })
        
        return components
    
    def extract_sidebar_components(self, soup, url):
        """Extract sidebar components"""
        sidebars = soup.find_all(['aside', 'div'], class_=re.compile(r'sidebar|aside|secondary', re.I))
        components = []
        
        for i, sidebar in enumerate(sidebars[:5]):  # Limit to 5 sidebars
            components.append({
                'id': f'sidebar_{i+1}',
                'html': str(sidebar),
                'classes': sidebar.get('class', []),
                'tag': sidebar.name,
                'widgets': len(sidebar.find_all(['div', 'section'], class_=re.compile(r'widget|module', re.I))),
                'text_content': sidebar.get_text()[:200]
            })
        
        return components
    
    def extract_modal_components(self, soup, url):
        """Extract modal/dialog components"""
        modals = soup.find_all(['div', 'dialog'], class_=re.compile(r'modal|dialog|popup|overlay', re.I))
        components = []
        
        for i, modal in enumerate(modals[:5]):  # Limit to 5 modals
            components.append({
                'id': f'modal_{i+1}',
                'html': str(modal),
                'classes': modal.get('class', []),
                'tag': modal.name,
                'buttons': len(modal.find_all(['button', 'input'])),
                'text_content': modal.get_text()[:200]
            })
        
        return components
    
    def extract_button_components(self, soup, url):
        """Extract button components"""
        buttons = soup.find_all(['button', 'input', 'a'], class_=re.compile(r'btn|button', re.I))
        components = []
        
        for i, button in enumerate(buttons[:20]):  # Limit to 20 buttons
            components.append({
                'id': f'button_{i+1}',
                'html': str(button),
                'classes': button.get('class', []),
                'tag': button.name,
                'type': button.get('type', ''),
                'href': button.get('href', ''),
                'text_content': button.get_text().strip()[:50]
            })
        
        return components
    
    def extract_breadcrumb_components(self, soup, url):
        """Extract breadcrumb components"""
        breadcrumbs = soup.find_all(['nav', 'ol', 'ul', 'div'], class_=re.compile(r'breadcrumb|crumb', re.I))
        components = []
        
        for i, breadcrumb in enumerate(breadcrumbs[:3]):  # Limit to 3 breadcrumbs
            components.append({
                'id': f'breadcrumb_{i+1}',
                'html': str(breadcrumb),
                'classes': breadcrumb.get('class', []),
                'tag': breadcrumb.name,
                'items': len(breadcrumb.find_all(['li', 'a'])),
                'text_content': breadcrumb.get_text()[:100]
            })
        
        return components
    
    def save_component_html(self, components, component_type, components_dir):
        """Save component HTML to files"""
        if not components:
            return
        
        # Create component type directory
        type_dir = components_dir / component_type
        type_dir.mkdir(exist_ok=True)
        
        # Save individual components
        for component in components:
            component_file = type_dir / f"{component['id']}.html"
            
            # Create a complete HTML document for the component
            html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{component_type.title()} Component - {component['id']}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .component-info {{ background: #f5f5f5; padding: 10px; margin-bottom: 20px; border-radius: 5px; }}
        .component-content {{ border: 1px solid #ddd; padding: 10px; border-radius: 5px; }}
    </style>
</head>
<body>
    <div class="component-info">
        <h2>{component_type.title()} Component</h2>
        <p><strong>ID:</strong> {component['id']}</p>
        <p><strong>Tag:</strong> {component.get('tag', 'N/A')}</p>
        <p><strong>Classes:</strong> {', '.join(component.get('classes', []))}</p>
        <p><strong>Text Preview:</strong> {component.get('text_content', 'N/A')[:100]}...</p>
    </div>
    <div class="component-content">
        {component['html']}
    </div>
</body>
</html>"""
            
            with open(component_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
        
        # Save component summary
        summary_file = type_dir / 'component_summary.json'
        summary_data = {
            'component_type': component_type,
            'total_components': len(components),
            'components': [
                {
                    'id': comp['id'],
                    'tag': comp.get('tag', ''),
                    'classes': comp.get('classes', []),
                    'text_preview': comp.get('text_content', '')[:100]
                }
                for comp in components
            ]
        }
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, indent=2, ensure_ascii=False)
    
    def create_component_index(self, components_dir, page_dir):
        """Create an index of all extracted components"""
        component_index = {
            'extraction_timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'component_types': {},
            'total_components': 0
        }
        
        # Scan component directories
        for component_type_dir in components_dir.iterdir():
            if component_type_dir.is_dir():
                component_type = component_type_dir.name
                html_files = list(component_type_dir.glob('*.html'))
                
                component_index['component_types'][component_type] = {
                    'count': len(html_files),
                    'files': [f.name for f in html_files]
                }
                component_index['total_components'] += len(html_files)
        
        # Save component index
        with open(page_dir / 'component_index.json', 'w', encoding='utf-8') as f:
            json.dump(component_index, f, indent=2, ensure_ascii=False)
        
        # Create HTML index page
        self.create_html_component_index(component_index, components_dir, page_dir)
    
    def create_html_component_index(self, component_index, components_dir, page_dir):
        """Create an HTML index page for easy component browsing"""
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Component Index - {page_dir.name}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .header {{ background: #333; color: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; }}
        .component-type {{ background: white; margin: 10px 0; padding: 15px; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        .component-type h3 {{ margin-top: 0; color: #333; }}
        .component-list {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }}
        .component-item {{ background: #f9f9f9; padding: 10px; border-radius: 3px; border-left: 4px solid #007cba; }}
        .component-item a {{ text-decoration: none; color: #007cba; font-weight: bold; }}
        .component-item a:hover {{ text-decoration: underline; }}
        .stats {{ background: #e7f3ff; padding: 10px; border-radius: 5px; margin-bottom: 20px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Component Index</h1>
        <p>Page: {page_dir.name}</p>
        <p>Extracted: {component_index['extraction_timestamp']}</p>
    </div>
    
    <div class="stats">
        <h2>Summary</h2>
        <p><strong>Total Components:</strong> {component_index['total_components']}</p>
        <p><strong>Component Types:</strong> {len(component_index['component_types'])}</p>
    </div>
"""
        
        for component_type, type_data in component_index['component_types'].items():
            html_content += f"""
    <div class="component-type">
        <h3>{component_type.title()} ({type_data['count']} components)</h3>
        <div class="component-list">
"""
            for file_name in type_data['files']:
                component_id = file_name.replace('.html', '')
                html_content += f"""
            <div class="component-item">
                <a href="components/{component_type}/{file_name}" target="_blank">{component_id}</a>
            </div>
"""
            html_content += """
        </div>
    </div>
"""
        
        html_content += """
</body>
</html>"""
        
        # Save HTML index
        with open(page_dir / 'component_index.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
    
    def extract_and_analyze_single_url(self, url, is_dynamic=False):
        """Extract HTML and perform comprehensive component analysis for a single URL"""
        try:
            # Create page identifier and directory
            page_id = self.create_page_identifier(url)
            page_dir = Path(self.output_dir) / page_id
            page_dir.mkdir(exist_ok=True)
            
            # Check if already processed
            analysis_file = page_dir / 'comprehensive_analysis.json'
            if analysis_file.exists():
                self.logger.info(f"⏭️  Skipping {url} - already processed")
                return True
            
            # Fetch the page
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Save raw HTML
            with open(page_dir / 'page.html', 'w', encoding='utf-8') as f:
                f.write(soup.prettify())
            
            # Extract and save HTML components
            self.extract_and_save_html_components(soup, page_dir, url)
            
            # Save URL info
            url_info = {
                'original_url': url,
                'page_identifier': page_id,
                'is_dynamic': is_dynamic,
                'status_code': response.status_code,
                'content_type': response.headers.get('content-type', ''),
                'content_length': len(response.content),
                'extraction_timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            
            with open(page_dir / 'url_info.json', 'w', encoding='utf-8') as f:
                json.dump(url_info, f, indent=2, ensure_ascii=False)
            
            # Perform comprehensive analysis using all strategies
            comprehensive_analysis = {
                'url': url,
                'page_id': page_id,
                'is_dynamic': is_dynamic,
                'analysis_timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'strategies': {}
            }
            
            for strategy_name, strategy_func in self.analysis_strategies.items():
                try:
                    analysis_result = strategy_func(soup, url)
                    comprehensive_analysis['strategies'][strategy_name] = analysis_result
                    
                    # Save individual strategy results
                    with open(page_dir / f'{strategy_name}_analysis.json', 'w', encoding='utf-8') as f:
                        json.dump(analysis_result, f, indent=2, ensure_ascii=False)
                        
                except Exception as e:
                    self.logger.error(f"Error in {strategy_name} analysis for {url}: {e}")
                    comprehensive_analysis['strategies'][strategy_name] = {'error': str(e)}
            
            # Save comprehensive analysis
            with open(analysis_file, 'w', encoding='utf-8') as f:
                json.dump(comprehensive_analysis, f, indent=2, ensure_ascii=False)
            
            with self.lock:
                self.logger.info(f"✅ Analyzed: {url} -> {page_id} {'(Dynamic)' if is_dynamic else ''}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error analyzing {url}: {e}")
            return False
    
    def analyze_all_urls(self, max_workers=5):
        """Analyze all URLs with comprehensive component analysis"""
        urls, dynamic_urls = self.load_urls()
        if not urls:
            self.logger.error("No URLs to process")
            return
        
        # Create set of dynamic URLs for quick lookup
        dynamic_url_set = set(dynamic_urls)
        
        self.logger.info(f"🚀 Starting comprehensive analysis of {len(urls)} URLs with {max_workers} workers")
        self.logger.info(f"📊 Dynamic URLs: {len(dynamic_urls)}, Static URLs: {len(urls) - len(dynamic_url_set)}")
        
        success_count = 0
        failed_count = 0
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_url = {
                executor.submit(self.extract_and_analyze_single_url, url, url in dynamic_url_set): url 
                for url in urls
            }
            
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
        
        # Generate comprehensive summary
        self.generate_comprehensive_summary(urls, dynamic_urls, success_count, failed_count)
        
        # Final summary
        self.logger.info(f"🎉 Comprehensive analysis complete!")
        self.logger.info(f"✅ Successful: {success_count}")
        self.logger.info(f"❌ Failed: {failed_count}")
        self.logger.info(f"📁 Output directory: {self.output_dir}")
    
    def generate_comprehensive_summary(self, urls, dynamic_urls, success_count, failed_count):
        """Generate a comprehensive summary of all analyses"""
        summary = {
            'analysis_overview': {
                'total_urls': len(urls),
                'dynamic_urls': len(dynamic_urls),
                'static_urls': len(urls) - len(set(dynamic_urls)),
                'successful_analyses': success_count,
                'failed_analyses': failed_count,
                'success_rate': success_count / len(urls) if urls else 0
            },
            'analysis_strategies': list(self.analysis_strategies.keys()),
            'output_structure': {
                'individual_page_folders': success_count,
                'files_per_page': [
                    'page.html',
                    'url_info.json',
                    'comprehensive_analysis.json',
                    'component_index.json',
                    'component_index.html',
                    'components/ (folder with extracted HTML components)'
                ] + [f'{strategy}_analysis.json' for strategy in self.analysis_strategies.keys()]
            },
            'component_extraction': {
                'component_types': [
                    'headers', 'navigation', 'main_content', 'articles', 'cards',
                    'forms', 'tables', 'lists', 'media', 'footers', 'sidebars',
                    'modals', 'buttons', 'breadcrumbs'
                ],
                'html_files_per_component': 'Individual HTML files for each component',
                'component_summaries': 'JSON summaries for each component type'
            },
            'analysis_timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Save comprehensive summary
        with open(Path(self.output_dir) / 'comprehensive_summary.json', 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"📋 Comprehensive summary saved to {self.output_dir}/comprehensive_summary.json")

if __name__ == "__main__":
    print("🔧 Advanced Component Analyzer - Multi-Strategy Analysis Tool with HTML Component Extraction")
    print("=" * 80)
    
    # Configuration
    crawled_file = input("Enter crawled URLs file (default: crawled_urls.json): ").strip() or "crawled_urls.json"
    output_dir = input("Enter output directory (default: advanced_extracted_html): ").strip() or "advanced_extracted_html"
    max_workers = int(input("Enter max concurrent workers (default: 4): ") or 4)
    
    # Create analyzer
    analyzer = AdvancedComponentAnalyzer(crawled_urls_file=crawled_file, output_dir=output_dir)
    
    print(f"\n🔍 Starting comprehensive HTML extraction and component analysis")
    print(f"📂 Input file: {crawled_file}")
    print(f"📁 Output directory: {output_dir}")
    print(f"⚡ Workers: {max_workers}")
    print(f"🧠 Analysis strategies: {len(analyzer.analysis_strategies)}")
    print("   • Semantic Analysis (HTML5, Schema.org, OpenGraph)")
    print("   • Structural Analysis (DOM depth, element distribution)")
    print("   • Content Type Analysis (text, media, interactive)")
    print("   • Interactive Elements Analysis (forms, navigation)")
    print("   • Layout Analysis (CSS frameworks, responsive design)")
    print("   • SEO Analysis (meta tags, headings, optimization)")
    print("   • Accessibility Analysis (ARIA, semantic structure)")
    print("   • Performance Analysis (resource hints, optimization)")
    print(f"🎨 Component extraction: 14 component types")
    print("   • Headers, Navigation, Main Content, Articles, Cards")
    print("   • Forms, Tables, Lists, Media, Footers, Sidebars")
    print("   • Modals, Buttons, Breadcrumbs")
    print("=" * 80)
    
    # Start analysis
    analyzer.analyze_all_urls(max_workers=max_workers)
    
    print(f"\n📁 Check the '{output_dir}' folder for comprehensive analysis results!")
    print("Each page has its own folder with:")
    print("  • page.html - Raw HTML content")
    print("  • url_info.json - Page metadata")
    print("  • comprehensive_analysis.json - All strategies combined")
    print("  • Individual strategy files (semantic_analysis.json, etc.)")
    print("  • component_index.html - Visual component browser")
    print("  • component_index.json - Component metadata")
    print("  • components/ folder with 14 component types:")
    print("    - Each component type has its own subfolder")
    print("    - Individual HTML files for each extracted component")
    print("    - Component summaries in JSON format")
    print("  • comprehensive_summary.json - Overall analysis summary")