"""Logging configuration for production use"""
import logging
import sys
from pathlib import Path
from datetime import datetime


class ProductionFilter(logging.Filter):
    """Filter out debug and verbose logging in production"""
    
    def filter(self, record):
        # Hide debug messages from all modules
        if record.levelno <= logging.DEBUG:
            return False
        
        # Hide warnings from specific libraries
        if record.name.startswith('urllib3') or record.name.startswith('requests'):
            return record.levelno >= logging.ERROR
        
        # Hide all scrapers internal logging except errors
        if 'scraper' in record.name.lower():
            return record.levelno >= logging.ERROR
            
        return True


def setup_logging(debug: bool = False, log_file: Path = None):
    """
    Configure logging for the application
    
    Args:
        debug: Enable debug logging
        log_file: Optional file to write logs to
    """
    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Minimal console formatter for production
    console_formatter = logging.Formatter('%(message)s')
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if debug else logging.WARNING)
    console_handler.setFormatter(console_formatter)
    
    if not debug:
        # Add production filter to hide internal messages
        console_handler.addFilter(ProductionFilter())
    
    root_logger.addHandler(console_handler)
    
    # File handler (if requested)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
    
    # Suppress specific library warnings
    logging.getLogger('urllib3').setLevel(logging.ERROR)
    logging.getLogger('requests').setLevel(logging.ERROR)
    logging.getLogger('fuzzywuzzy').setLevel(logging.ERROR)
    
    # Suppress BeautifulSoup warnings
    import warnings
    warnings.filterwarnings('ignore', category=UserWarning, module='bs4')


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name"""
    return logging.getLogger(name)