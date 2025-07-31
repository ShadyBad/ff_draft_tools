"""Base scraper class for all ranking sources"""
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
import time

import requests
from bs4 import BeautifulSoup

from config import CACHE_DIR, CACHE_EXPIRY_HOURS
from src.core.models import Ranking
from src.utils.cache import OptimizedCache
from src.utils.monitoring import monitor


logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Base class for all ranking scrapers"""
    
    def __init__(self, source_name: str, cache_hours: int = CACHE_EXPIRY_HOURS):
        self.source_name = source_name
        self.cache_hours = cache_hours
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        # Initialize optimized cache for this scraper
        self.cache = OptimizedCache(f'scraper_{source_name}', cache_hours=cache_hours)
    
    @abstractmethod
    def scrape_rankings(self) -> List[Ranking]:
        """Scrape rankings from the source"""
        pass
    
    def fetch(self, force_refresh: bool = False) -> List[Ranking]:
        """Fetch rankings with optimized caching and performance monitoring"""
        with monitor.measure(f"fetch_{self.source_name}", source=self.source_name):
            # Generate cache key based on date to ensure daily updates
            date_str = datetime.now().strftime("%Y%m%d")
            cache_key = f"{self.source_name}_rankings_{date_str}"
            
            # Check cache first if not forcing refresh
            if not force_refresh:
                with monitor.measure(f"cache_check_{self.source_name}"):
                    cached_rankings = self.cache.get(cache_key)
                    if cached_rankings is not None:
                        logger.info(f"Loading {self.source_name} rankings from optimized cache")
                        return cached_rankings
            
            # Scrape fresh data
            logger.info(f"Scraping fresh {self.source_name} rankings")
            try:
                with monitor.measure(f"scrape_{self.source_name}"):
                    rankings = self.scrape_rankings()
                
                # Save to optimized cache
                if rankings:
                    with monitor.measure(f"cache_save_{self.source_name}"):
                        self.cache.set(cache_key, rankings, cache_hours=self.cache_hours)
                
                return rankings
            except Exception as e:
                logger.error(f"Error scraping {self.source_name}: {e}")
                
                # Try to get any cached data (even if expired) as fallback
                cached_rankings = self.cache.get(cache_key)
                if cached_rankings is not None:
                    logger.warning(f"Using cached {self.source_name} rankings after scraping error")
                    return cached_rankings
                
                raise
    
    def _get_page(self, url: str, delay: float = 1.0) -> BeautifulSoup:
        """Get and parse a web page"""
        time.sleep(delay)  # Be respectful
        
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        
        return BeautifulSoup(response.content, 'html.parser')
    
