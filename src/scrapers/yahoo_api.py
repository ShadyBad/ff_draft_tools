"""Yahoo Fantasy Football API integration"""
import json
import logging
import os
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime
import xml.etree.ElementTree as ET

import requests

from src.scrapers.base import BaseScraper
from src.scrapers.yahoo_oauth import YahooOAuth
from src.core.models import Player, Ranking, Position, NFLTeam
from config import DATA_DIR, SEASON_YEAR


logger = logging.getLogger(__name__)


class YahooAPIScraper(BaseScraper):
    """Scraper for Yahoo Fantasy Football using official API"""
    
    FANTASY_API_BASE = "https://fantasysports.yahooapis.com/fantasy/v2"
    
    def __init__(self):
        super().__init__('yahoo_api', cache_hours=6)
        
        # Yahoo OAuth credentials
        self.client_id = os.getenv('YAHOO_CLIENT_ID')
        self.client_secret = os.getenv('YAHOO_CLIENT_SECRET')
        
        # Initialize OAuth handler
        if self.client_id and self.client_secret:
            self.oauth = YahooOAuth(self.client_id, self.client_secret)
        else:
            self.oauth = None
            logger.warning("Yahoo API credentials not found in environment variables")
    
    def _make_request(self, endpoint: str) -> Optional[ET.Element]:
        """Make authenticated request to Yahoo Fantasy API"""
        if not self.oauth:
            return None
        
        try:
            headers = self.oauth.get_auth_header()
            headers['Accept'] = 'application/xml'
            
            url = f"{self.FANTASY_API_BASE}/{endpoint}"
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                # Parse XML response
                root = ET.fromstring(response.content)
                return root
            else:
                logger.error(f"API request failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error making API request: {e}")
            return None
    
    def scrape_rankings(self) -> List[Ranking]:
        """Scrape rankings from Yahoo Fantasy API"""
        if not self.oauth:
            logger.warning("Yahoo API authentication not available")
            return []
        
        rankings = []
        
        try:
            # Authenticate
            if not self.oauth.authenticate():
                logger.error("Yahoo authentication failed")
                return []
            
            logger.info("Fetching rankings from Yahoo Fantasy API")
            
            # Get NFL game key for current season
            game_key = self._get_nfl_game_key()
            if not game_key:
                logger.error("Could not determine NFL game key")
                return []
            
            # Get player rankings
            rankings = self._fetch_player_rankings(game_key)
            
            logger.info(f"Fetched {len(rankings)} players from Yahoo API")
            
        except Exception as e:
            logger.error(f"Error fetching from Yahoo API: {e}")
            return []
        
        return rankings
    
    def _get_nfl_game_key(self) -> Optional[str]:
        """Get the game key for NFL fantasy football for current season"""
        try:
            # Yahoo uses game IDs for different seasons
            # NFL 2024 = 423, NFL 2025 = 449 (estimated)
            game_ids = {
                2024: "423",
                2025: "449",  # This will need to be updated when Yahoo releases 2025
                2026: "475",  # Estimated
            }
            
            game_id = game_ids.get(SEASON_YEAR, "449")
            
            # Verify the game exists
            root = self._make_request(f"game/nfl")
            if root:
                return f"nfl"  # For current season
            
            # Try specific game ID
            return game_id
            
        except Exception as e:
            logger.error(f"Error getting game key: {e}")
            # Default to estimated 2025 game ID
            return "449"
    
    def _fetch_player_rankings(self, game_key: str) -> List[Ranking]:
        """Fetch player rankings from Yahoo"""
        rankings = []
        
        try:
            # Yahoo limits to 25 players per request, so we need pagination
            start = 0
            count = 25
            max_players = 300
            
            while start < max_players:
                # Request players with their stats and projections
                endpoint = f"game/{game_key}/players;start={start};count={count}/stats"
                root = self._make_request(endpoint)
                
                if not root:
                    break
                
                # Parse players from XML
                # Yahoo XML namespace
                ns = {'fantasy': 'http://fantasysports.yahooapis.com/fantasy/v2/base.rng'}
                
                players = root.findall('.//fantasy:player', ns)
                if not players:
                    # Try without namespace
                    players = root.findall('.//player')
                
                if not players:
                    logger.warning("No players found in response")
                    break
                
                for player_elem in players:
                    ranking = self._parse_player_xml(player_elem, len(rankings) + 1)
                    if ranking:
                        rankings.append(ranking)
                
                # Check if we got all players
                if len(players) < count:
                    break
                
                start += count
            
        except Exception as e:
            logger.error(f"Error fetching player rankings: {e}")
        
        # If we couldn't get API rankings, fall back to web scraping
        if not rankings:
            logger.info("No API rankings available, using web scraper fallback")
            from src.scrapers.yahoo import YahooScraper
            scraper = YahooScraper()
            return scraper.scrape_rankings()
        
        return rankings
    
    def _parse_player_xml(self, player_elem: ET.Element, rank: int) -> Optional[Ranking]:
        """Parse Yahoo player XML into Ranking"""
        try:
            # Extract player information from XML
            name = self._get_text(player_elem, './/name/full')
            if not name:
                return None
            
            # Position
            positions = self._get_text(player_elem, './/display_position')
            position = self._parse_position(positions)
            if not position:
                return None
            
            # Team
            team_abbr = self._get_text(player_elem, './/editorial_team_abbr')
            team = self._parse_team(team_abbr)
            if not team:
                team = NFLTeam.FA  # Free agent
            
            # Bye week
            bye_week = int(self._get_text(player_elem, './/bye_weeks/week', '0'))
            
            # Player ID
            player_id = self._get_text(player_elem, './/player_id')
            
            # Create player
            player = Player(
                name=name,
                position=position,
                team=team,
                bye_week=bye_week,
                player_id=f"yahoo_{player_id}" if player_id else None
            )
            
            # Get projected points if available
            proj_points = float(self._get_text(player_elem, './/player_points/total', '0'))
            
            # Create ranking
            ranking = Ranking(
                player=player,
                rank=rank,
                source='yahoo_api',
                projected_points=proj_points if proj_points > 0 else None
            )
            
            return ranking
            
        except Exception as e:
            logger.debug(f"Error parsing player XML: {e}")
            return None
    
    def _get_text(self, elem: ET.Element, xpath: str, default: str = '') -> str:
        """Get text from XML element"""
        try:
            found = elem.find(xpath)
            if found is not None and found.text:
                return found.text.strip()
        except:
            pass
        return default
    
    def _parse_position(self, pos_str: str) -> Optional[Position]:
        """Parse position string"""
        if not pos_str:
            return None
        
        # Handle comma-separated positions (e.g., "RB,WR")
        positions = pos_str.split(',')
        primary_pos = positions[0].strip().upper()
        
        pos_map = {
            'QB': Position.QB,
            'RB': Position.RB,
            'WR': Position.WR,
            'TE': Position.TE,
            'K': Position.K,
            'DEF': Position.DST,
            'DST': Position.DST,
            'D/ST': Position.DST,
        }
        return pos_map.get(primary_pos)
    
    def _parse_team(self, team_str: str) -> Optional[NFLTeam]:
        """Parse team string"""
        if not team_str:
            return None
        
        # Yahoo sometimes uses different abbreviations
        team_mappings = {
            'JAC': 'JAX',
            'WSH': 'WAS',
        }
        
        team_str = team_mappings.get(team_str.upper(), team_str.upper())
        
        try:
            return NFLTeam(team_str)
        except ValueError:
            if team_str == 'FA':  # Free agent
                return NFLTeam.FA
            logger.warning(f"Unknown Yahoo team: {team_str}")
            return None


def test_yahoo_api():
    """Test Yahoo API connection"""
    print("\nTesting Yahoo Fantasy API...")
    print("="*60)
    
    # Check for credentials
    client_id = os.getenv('YAHOO_CLIENT_ID')
    client_secret = os.getenv('YAHOO_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        print("\n❌ Yahoo API credentials not found!")
        print("\nTo set up Yahoo API:")
        print("1. Go to https://developer.yahoo.com/apps/")
        print("2. Create a new app with Fantasy Sports read permissions")
        print("3. Add to your .env file:")
        print("   YAHOO_CLIENT_ID=your_client_id")
        print("   YAHOO_CLIENT_SECRET=your_client_secret")
        return
    
    print("✓ Yahoo API credentials found")
    
    # Try to authenticate
    scraper = YahooAPIScraper()
    if scraper.oauth and scraper.oauth.authenticate():
        print("✓ Yahoo authentication successful!")
        
        # Try to fetch some data
        rankings = scraper.scrape_rankings()
        if rankings:
            print(f"✓ Successfully fetched {len(rankings)} players")
            print("\nTop 5 players:")
            for r in rankings[:5]:
                print(f"  {r.rank}. {r.player.name} ({r.player.position.value}) - {r.player.team.value}")
        else:
            print("⚠️  No rankings fetched (API might not have 2025 data yet)")
    else:
        print("❌ Yahoo authentication failed")


if __name__ == "__main__":
    # Run test
    test_yahoo_api()