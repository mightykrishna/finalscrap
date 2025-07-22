"""
Configuration and utility functions for the web crawler
"""

class CrawlerConfig:
    """Configuration class for customizing crawler behavior"""
    
    # Common pagination button selectors
    PAGINATION_SELECTORS = [
        "//a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'next')]",
        "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'next')]",
        "//a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'previous')]",
        "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'previous')]",
        "//a[contains(@class, 'next') or contains(@class, 'pagination-next')]",
        "//button[contains(@class, 'next') or contains(@class, 'pagination-next')]",
        "//a[contains(@class, 'prev') or contains(@class, 'pagination-prev')]",
        "//button[contains(@class, 'prev') or contains(@class, 'pagination-prev')]",
        "//a[@aria-label='Next page' or @aria-label='Previous page']",
        "//button[@aria-label='Next page' or @aria-label='Previous page']"
    ]
    
    # Load more button selectors
    LOAD_MORE_SELECTORS = [
        "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'load more')]",
        "//a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'load more')]",
        "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'show more')]",
        "//a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'show more')]",
        "//button[contains(@class, 'load-more') or contains(@class, 'show-more')]",
        "//a[contains(@class, 'load-more') or contains(@class, 'show-more')]"
    ]
    
    # Interactive elements that might load content
    INTERACTIVE_SELECTORS = [
        "//div[contains(@class, 'carousel') or contains(@class, 'slider')]",
        "//button[contains(@class, 'tab') or @role='tab']",
        "//a[contains(@class, 'tab') or @role='tab']",
        "//div[contains(@class, 'accordion')]",
        "//button[contains(@class, 'dropdown') or @aria-haspopup='true']"
    ]
    
    # Default Chrome options
    CHROME_OPTIONS = [
        "--no-sandbox",
        "--disable-dev-shm-usage", 
        "--disable-gpu",
        "--window-size=1920,1080",
        "--disable-blink-features=AutomationControlled",
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    ]

def create_sample_config():
    """Create a sample configuration file"""
    sample_config = {
        "base_url": "https://example.com",
        "max_depth": 2,
        "delay": 2,
        "headless": True,
        "output_file": "crawled_data.json",
        "custom_selectors": {
            "pagination": [],
            "load_more": [],
            "interactive": []
        },
        "exclude_patterns": [
            "*/admin/*",
            "*/login/*",
            "*/logout/*",
            "*.pdf",
            "*.jpg",
            "*.png"
        ]
    }
    
    import json
    with open('crawler_config.json', 'w') as f:
        json.dump(sample_config, f, indent=2)
    
    print("Sample configuration created: crawler_config.json")

if __name__ == "__main__":
    create_sample_config()