"""Data scrapers for fantasy football rankings"""
from .base import BaseScraper
from .fantasypros import FantasyProsScraper
from .espn import ESPNScraper
from .nfl import NFLScraper
from .cbs import CBSScraper

__all__ = ['BaseScraper', 'FantasyProsScraper', 'ESPNScraper', 'NFLScraper', 'CBSScraper']