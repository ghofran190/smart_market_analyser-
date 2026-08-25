# scraping/__init__.py
"""Package pour le crawling et le scraping de données."""

try:
    from .content_cleaner import ContentCleaner
except ImportError:
    pass

try:
    from .firecrawl_scraper import FirecrawlMarkdownCollector
except ImportError:
    pass

from .models import ScrapingStats, CleaningResult

__all__ = [
    'ContentCleaner',
    'FirecrawlMarkdownCollector',
    'ScrapingStats',
    'CleaningResult',
]