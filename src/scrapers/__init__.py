"""Data scrapers for fantasy football rankings"""
from .base import BaseScraper
from .fantasypros import FantasyProsScraper
from .espn import ESPNScraper

__all__ = ['BaseScraper', 'FantasyProsScraper', 'ESPNScraper']