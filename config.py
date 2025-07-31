"""Configuration settings for FF Draft Tools"""
from datetime import datetime
import os
from pathlib import Path

# Project paths
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
OUTPUT_DIR = DATA_DIR / "output"

# Ensure directories exist
CACHE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Season settings
SEASON_YEAR = 2025
SEASON_START = datetime(2025, 9, 4)  # NFL 2025 season start (estimated)

# Default league settings
DEFAULT_SETTINGS = {
    "scoring": "HALF_PPR",
    "teams": 12,
    "roster": {
        "QB": 1,
        "RB": 2,
        "WR": 2,
        "TE": 1,
        "FLEX": 1,
        "K": 1,
        "DST": 1,
        "BENCH": 6
    },
    "draft_rounds": 15
}

# Scoring systems
SCORING_SYSTEMS = {
    "STANDARD": {
        "pass_td": 4,
        "pass_yds": 0.04,
        "pass_int": -2,
        "rush_td": 6,
        "rush_yds": 0.1,
        "rec_td": 6,
        "rec_yds": 0.1,
        "receptions": 0,
        "fumble": -2
    },
    "HALF_PPR": {
        "pass_td": 4,
        "pass_yds": 0.04,
        "pass_int": -2,
        "rush_td": 6,
        "rush_yds": 0.1,
        "rec_td": 6,
        "rec_yds": 0.1,
        "receptions": 0.5,
        "fumble": -2
    },
    "PPR": {
        "pass_td": 4,
        "pass_yds": 0.04,
        "pass_int": -2,
        "rush_td": 6,
        "rush_yds": 0.1,
        "rec_td": 6,
        "rec_yds": 0.1,
        "receptions": 1.0,
        "fumble": -2
    }
}

# Data source configurations
RANKING_SOURCES = {
    "fantasypros": {
        "url": "https://www.fantasypros.com/nfl/rankings/consensus-cheatsheets.php",
        "weight": 1.0,
        "cache_hours": 6
    },
    "yahoo": {
        "url": "https://football.fantasysports.yahoo.com/f1/draftanalysis",
        "weight": 0.8,
        "cache_hours": 12
    },
    "espn": {
        "url": "https://fantasy.espn.com/football/players/projections",
        "weight": 0.9,
        "cache_hours": 12
    },
    "nfl": {
        "url": "https://www.nfl.com/news/2025-nfl-fantasy-football-rankings",
        "weight": 1.0,
        "cache_hours": 12
    },
    "cbs": {
        "url": "https://www.cbssports.com/fantasy/football/rankings/",
        "weight": 0.95,
        "cache_hours": 12
    }
}

# Platform presets for quick setup
PLATFORM_PRESETS = {
    "espn_standard": {
        "scoring": "STANDARD",
        "teams": 10,
        "roster": {
            "QB": 1, "RB": 2, "WR": 2, "TE": 1,
            "FLEX": 1, "K": 1, "DST": 1, "BENCH": 7
        }
    },
    "yahoo_half_ppr": {
        "scoring": "HALF_PPR",
        "teams": 12,
        "roster": {
            "QB": 1, "RB": 2, "WR": 3, "TE": 1,
            "FLEX": 1, "K": 1, "DST": 1, "BENCH": 5
        }
    },
    "sleeper_ppr": {
        "scoring": "PPR",
        "teams": 12,
        "roster": {
            "QB": 1, "RB": 2, "WR": 2, "TE": 1,
            "FLEX": 2, "K": 1, "DST": 1, "BENCH": 5
        }
    }
}

# Cache settings
CACHE_EXPIRY_HOURS = 6
MAX_CACHE_AGE_DAYS = 3

# Google Sheets settings
GOOGLE_SHEETS_SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file'
]
SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE', 'credentials/service_account.json')

# Web interface settings
FLASK_HOST = "127.0.0.1"
FLASK_PORT = 5000
FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

# Tier breakpoints (customizable)
DEFAULT_TIER_SIZES = {
    "QB": [6, 6, 6, 6],  # 4 tiers of 6 QBs each
    "RB": [8, 12, 16, 20],  # Larger tiers as we go down
    "WR": [8, 12, 16, 20],
    "TE": [4, 6, 8, 10],
    "K": [8, 8, 8],
    "DST": [8, 8, 8]
}