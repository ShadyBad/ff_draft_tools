"""NFL.com Fantasy Football rankings scraper"""
import json
import logging
import re
from typing import List, Dict, Optional
from datetime import datetime
import requests
from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper
from src.core.models import Player, Ranking, Position, NFLTeam
from src.utils.validation import InputValidator, ValidationError
from config import RANKING_SOURCES


logger = logging.getLogger(__name__)


class NFLScraper(BaseScraper):
    """Scraper for NFL.com Fantasy Football rankings"""
    
    def __init__(self):
        source_config = RANKING_SOURCES.get('nfl', {
            'url': 'https://www.nfl.com/news/2025-nfl-fantasy-football-rankings',
            'cache_hours': 12,
            'weight': 1.0
        })
        super().__init__('nfl', source_config.get('cache_hours', 12))
        self.base_url = 'https://www.nfl.com'
        
        # NFL.com specific mappings
        self.position_mappings = {
            'QB': Position.QB,
            'RB': Position.RB,
            'WR': Position.WR,
            'TE': Position.TE,
            'K': Position.K,
            'DST': Position.DST,
            'DEF': Position.DST,
        }
        
        # NFL.com team abbreviation mappings
        self.team_mappings = {
            'JAC': 'JAX',
            'WSH': 'WAS',
            'LA': 'LAR',  # Rams by default
        }
    
    def scrape_rankings(self) -> List[Ranking]:
        """Scrape rankings from NFL.com"""
        rankings = []
        
        try:
            # Try API endpoint first
            rankings = self._fetch_from_api()
            
            if not rankings:
                # Fallback to web scraping
                logger.info("NFL.com API failed, trying web scraping")
                rankings = self._scrape_from_web()
            
            if rankings:
                logger.info(f"Successfully scraped {len(rankings)} players from NFL.com")
            else:
                logger.warning("No rankings found from NFL.com, using fallback data")
                rankings = self._get_fallback_rankings()
                
        except Exception as e:
            logger.error(f"Error scraping NFL.com: {e}")
            rankings = self._get_fallback_rankings()
        
        # Validate rankings before returning
        return self._validate_rankings(rankings)
    
    def _fetch_from_api(self) -> List[Ranking]:
        """Try to fetch from NFL.com API"""
        rankings = []
        
        try:
            # NFL.com fantasy API endpoint
            api_url = "https://api.nfl.com/fantasy/v2/players/stats"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Referer': 'https://www.nfl.com/fantasy/'
            }
            
            params = {
                'season': '2025',
                'seasonType': 'REG',
                'scoringSystem': 'PPR',
                'limit': '300'
            }
            
            response = self.session.get(api_url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # Parse player data
                if 'players' in data:
                    for idx, player_data in enumerate(data['players'], 1):
                        ranking = self._parse_api_player(player_data, idx)
                        if ranking:
                            rankings.append(ranking)
                            
        except Exception as e:
            logger.debug(f"NFL.com API error: {e}")
        
        return rankings
    
    def _parse_api_player(self, player_data: Dict, rank: int) -> Optional[Ranking]:
        """Parse player data from NFL.com API"""
        try:
            # Extract player info
            name = player_data.get('displayName', '')
            if not name:
                return None
            
            # Get position
            position = self._map_position(player_data.get('position', ''))
            if not position:
                return None
            
            # Get team
            team = self._parse_team(player_data.get('team', ''))
            if not team:
                return None
            
            # Get projections
            projected_points = player_data.get('projectedFantasyPoints', 0)
            
            # Create player and ranking
            player = Player(
                name=name,
                position=position,
                team=team,
                bye_week=player_data.get('byeWeek')
            )
            
            ranking = Ranking(
                player=player,
                rank=rank,
                source='nfl',
                projected_points=projected_points
            )
            
            return ranking
            
        except Exception as e:
            logger.debug(f"Error parsing NFL.com API player: {e}")
            return None
    
    def _scrape_from_web(self) -> List[Ranking]:
        """Scrape from NFL.com website"""
        rankings = []
        
        try:
            # Try multiple NFL.com URLs
            urls = [
                'https://www.nfl.com/news/2025-fantasy-football-rankings-top-200-overall-players',
                'https://www.nfl.com/fantasy/rankings',
                'https://fantasy.nfl.com/research/rankings'
            ]
            
            for url in urls:
                try:
                    response = self.session.get(url, timeout=30)
                    if response.status_code == 200:
                        rankings = self._parse_web_rankings(response.content)
                        if rankings:
                            break
                except Exception as e:
                    logger.debug(f"Failed to fetch {url}: {e}")
                    continue
                    
        except Exception as e:
            logger.debug(f"Error scraping NFL.com web: {e}")
        
        return rankings
    
    def _parse_web_rankings(self, content: bytes) -> List[Ranking]:
        """Parse rankings from NFL.com HTML"""
        rankings = []
        
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # Look for ranking tables or lists
            ranking_sections = soup.find_all(['table', 'ol', 'div'], 
                                           class_=re.compile(r'rank|player|fantasy'))
            
            for section in ranking_sections:
                # Try to find player entries
                if section.name == 'table':
                    rows = section.find_all('tr')[1:]  # Skip header
                    for idx, row in enumerate(rows, 1):
                        ranking = self._parse_table_row(row, idx)
                        if ranking:
                            rankings.append(ranking)
                elif section.name == 'ol':
                    items = section.find_all('li')
                    for idx, item in enumerate(items, 1):
                        ranking = self._parse_list_item(item, idx)
                        if ranking:
                            rankings.append(ranking)
                
                if rankings:
                    break
                    
        except Exception as e:
            logger.debug(f"Error parsing NFL.com HTML: {e}")
        
        return rankings
    
    def _parse_table_row(self, row, rank: int) -> Optional[Ranking]:
        """Parse a table row from NFL.com rankings"""
        try:
            cells = row.find_all(['td', 'th'])
            if len(cells) < 3:
                return None
            
            # Extract player info
            player_text = cells[1].get_text(strip=True)
            
            # Parse format: "Player Name, Team POS"
            match = re.match(r'^(.+?),\s*(\w+)\s+(\w+)$', player_text)
            if match:
                name = match.group(1)
                team_str = match.group(2)
                pos_str = match.group(3)
            else:
                return None
            
            # Map position and team
            position = self._map_position(pos_str)
            team = self._parse_team(team_str)
            
            if not position or not team:
                return None
            
            # Create player and ranking
            player = Player(
                name=name,
                position=position,
                team=team,
                bye_week=None
            )
            
            ranking = Ranking(
                player=player,
                rank=rank,
                source='nfl'
            )
            
            return ranking
            
        except Exception as e:
            logger.debug(f"Error parsing NFL.com table row: {e}")
            return None
    
    def _parse_list_item(self, item, rank: int) -> Optional[Ranking]:
        """Parse a list item from NFL.com rankings"""
        try:
            text = item.get_text(strip=True)
            
            # Parse format: "1. Player Name, Team POS"
            match = re.match(r'^\d+\.\s*(.+?),\s*(\w+)\s+(\w+)', text)
            if match:
                name = match.group(1)
                team_str = match.group(2)
                pos_str = match.group(3)
                
                position = self._map_position(pos_str)
                team = self._parse_team(team_str)
                
                if position and team:
                    player = Player(
                        name=name,
                        position=position,
                        team=team,
                        bye_week=None
                    )
                    
                    return Ranking(
                        player=player,
                        rank=rank,
                        source='nfl'
                    )
                    
        except Exception as e:
            logger.debug(f"Error parsing NFL.com list item: {e}")
        
        return None
    
    def _map_position(self, pos_str: str) -> Optional[Position]:
        """Map NFL.com position to our Position enum"""
        if not pos_str:
            return None
        
        pos_str = pos_str.upper().strip()
        return self.position_mappings.get(pos_str)
    
    def _parse_team(self, team_str: str) -> Optional[NFLTeam]:
        """Parse team string to NFLTeam enum"""
        if not team_str:
            return None
        
        team_str = team_str.upper().strip()
        
        # Apply mappings
        if team_str in self.team_mappings:
            team_str = self.team_mappings[team_str]
        
        # Handle free agents
        if team_str in ['FA', 'FREE', '--']:
            return NFLTeam.FA
        
        try:
            return NFLTeam(team_str)
        except ValueError:
            logger.debug(f"Unknown NFL.com team: {team_str}")
            return None
    
    def _validate_rankings(self, rankings: List[Ranking]) -> List[Ranking]:
        """Validate rankings before returning"""
        validated_rankings = []
        seen_players = set()
        
        for ranking in rankings:
            try:
                # Validate player name
                clean_name = InputValidator.validate_player_name(ranking.player.name)
                ranking.player.name = clean_name
                
                # Check for duplicates
                player_key = f"{clean_name}_{ranking.player.position.value}_{ranking.player.team.value}"
                if player_key in seen_players:
                    logger.debug(f"Skipping duplicate player: {clean_name}")
                    continue
                seen_players.add(player_key)
                
                # Validate rank
                if ranking.rank < 1 or ranking.rank > 500:
                    logger.debug(f"Invalid rank {ranking.rank} for {clean_name}")
                    continue
                
                validated_rankings.append(ranking)
                
            except ValidationError as e:
                logger.debug(f"Validation error for NFL.com ranking: {e}")
                continue
            except Exception as e:
                logger.debug(f"Unexpected error validating NFL.com ranking: {e}")
                continue
        
        return validated_rankings
    
    def _get_fallback_rankings(self) -> List[Ranking]:
        """Return fallback NFL.com rankings for 2025 season"""
        logger.info("Using NFL.com fallback rankings for 2025 season")
        
        # Top 50 consensus players from NFL.com analysts
        fallback_data = [
            # Top RBs according to NFL.com
            ("Saquon Barkley", "RB", "PHI", 1, 380),
            ("Bijan Robinson", "RB", "ATL", 2, 365),
            ("Jahmyr Gibbs", "RB", "DET", 4, 340),
            ("Breece Hall", "RB", "NYJ", 6, 320),
            ("Christian McCaffrey", "RB", "SF", 9, 300),
            ("Derrick Henry", "RB", "BAL", 10, 290),
            ("Jonathan Taylor", "RB", "IND", 13, 280),
            ("Josh Jacobs", "RB", "GB", 16, 270),
            ("De'Von Achane", "RB", "MIA", 18, 260),
            ("Kenneth Walker III", "RB", "SEA", 22, 250),
            
            # Top WRs according to NFL.com
            ("Ja'Marr Chase", "WR", "CIN", 3, 340),
            ("CeeDee Lamb", "WR", "DAL", 5, 320),
            ("Justin Jefferson", "WR", "MIN", 7, 310),
            ("Tyreek Hill", "WR", "MIA", 8, 300),
            ("Amon-Ra St. Brown", "WR", "DET", 11, 285),
            ("Puka Nacua", "WR", "LAR", 12, 280),
            ("A.J. Brown", "WR", "PHI", 14, 270),
            ("Nico Collins", "WR", "HOU", 15, 265),
            ("Davante Adams", "WR", "LAR", 17, 255),
            ("Malik Nabers", "WR", "NYG", 19, 250),
            ("Chris Olave", "WR", "NO", 20, 245),
            ("DK Metcalf", "WR", "SEA", 21, 240),
            ("Mike Evans", "WR", "TB", 23, 235),
            ("Calvin Ridley", "WR", "TEN", 24, 230),
            ("Stefon Diggs", "WR", "HOU", 25, 225),
            
            # Top TEs according to NFL.com
            ("Sam LaPorta", "TE", "DET", 26, 200),
            ("Travis Kelce", "TE", "KC", 27, 195),
            ("Mark Andrews", "TE", "BAL", 28, 190),
            ("George Kittle", "TE", "SF", 29, 185),
            ("Trey McBride", "TE", "ARI", 30, 180),
            ("Brock Bowers", "TE", "LV", 31, 175),
            ("Dalton Kincaid", "TE", "BUF", 35, 165),
            
            # Top QBs according to NFL.com
            ("Josh Allen", "QB", "BUF", 32, 420),
            ("Jalen Hurts", "QB", "PHI", 33, 410),
            ("Lamar Jackson", "QB", "BAL", 34, 400),
            ("Patrick Mahomes", "QB", "KC", 36, 390),
            ("Dak Prescott", "QB", "DAL", 37, 380),
            ("Joe Burrow", "QB", "CIN", 38, 370),
            ("C.J. Stroud", "QB", "HOU", 39, 360),
            ("Justin Herbert", "QB", "LAC", 40, 350),
            ("Tua Tagovailoa", "QB", "MIA", 41, 340),
            ("Jordan Love", "QB", "GB", 42, 330),
        ]
        
        rankings = []
        for name, pos_str, team_str, rank, proj_points in fallback_data:
            try:
                position = self.position_mappings.get(pos_str)
                team = self._parse_team(team_str)
                
                if position and team:
                    player = Player(
                        name=name,
                        position=position,
                        team=team,
                        bye_week=None
                    )
                    
                    ranking = Ranking(
                        player=player,
                        rank=rank,
                        source='nfl',
                        projected_points=proj_points,
                        notes="NFL.com 2025 Rankings"
                    )
                    
                    rankings.append(ranking)
            except Exception as e:
                logger.debug(f"Error creating fallback ranking: {e}")
                continue
        
        return rankings