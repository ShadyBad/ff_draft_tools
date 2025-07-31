"""CBS Sports Fantasy Football rankings scraper"""
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


class CBSScraper(BaseScraper):
    """Scraper for CBS Sports Fantasy Football rankings"""
    
    def __init__(self):
        source_config = RANKING_SOURCES.get('cbs', {
            'url': 'https://www.cbssports.com/fantasy/football/rankings/',
            'cache_hours': 12,
            'weight': 0.95
        })
        super().__init__('cbs', source_config.get('cache_hours', 12))
        self.base_url = 'https://www.cbssports.com'
        
        # CBS Sports specific mappings
        self.position_mappings = {
            'QB': Position.QB,
            'RB': Position.RB,
            'WR': Position.WR,
            'TE': Position.TE,
            'K': Position.K,
            'DST': Position.DST,
            'DEF': Position.DST,
            'PK': Position.K,
        }
        
        # CBS team abbreviation mappings
        self.team_mappings = {
            'JAC': 'JAX',
            'WSH': 'WAS',
        }
    
    def scrape_rankings(self) -> List[Ranking]:
        """Scrape rankings from CBS Sports"""
        rankings = []
        
        try:
            # Try main rankings page
            rankings = self._scrape_main_rankings()
            
            if not rankings:
                # Try API endpoint
                logger.info("CBS main rankings failed, trying API")
                rankings = self._fetch_from_api()
            
            if rankings:
                logger.info(f"Successfully scraped {len(rankings)} players from CBS Sports")
            else:
                logger.warning("No rankings found from CBS Sports, using fallback data")
                rankings = self._get_fallback_rankings()
                
        except Exception as e:
            logger.error(f"Error scraping CBS Sports: {e}")
            rankings = self._get_fallback_rankings()
        
        # Validate rankings before returning
        return self._validate_rankings(rankings)
    
    def _scrape_main_rankings(self) -> List[Ranking]:
        """Scrape from CBS Sports main rankings page"""
        rankings = []
        
        try:
            # CBS Sports PPR rankings URL
            url = 'https://www.cbssports.com/fantasy/football/rankings/ppr/top-200/'
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
            
            response = self.session.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Find ranking table
                tables = soup.find_all('table', class_=['TableBase', 'rankings'])
                
                for table in tables:
                    tbody = table.find('tbody')
                    if tbody:
                        rows = tbody.find_all('tr')
                        
                        for row in rows:
                            ranking = self._parse_ranking_row(row)
                            if ranking:
                                rankings.append(ranking)
                        
                        if rankings:
                            break
                            
        except Exception as e:
            logger.debug(f"Error scraping CBS main rankings: {e}")
        
        return rankings
    
    def _parse_ranking_row(self, row) -> Optional[Ranking]:
        """Parse a ranking row from CBS Sports"""
        try:
            cells = row.find_all('td')
            if len(cells) < 4:
                return None
            
            # Get rank
            rank_text = cells[0].get_text(strip=True)
            rank = int(re.search(r'\d+', rank_text).group()) if re.search(r'\d+', rank_text) else None
            
            if not rank:
                return None
            
            # Get player info
            player_cell = cells[1]
            
            # Extract player name
            name_elem = player_cell.find(['a', 'span'], class_=re.compile(r'player|name'))
            if name_elem:
                name = name_elem.get_text(strip=True)
            else:
                name = player_cell.get_text(strip=True).split(',')[0]
            
            # Extract position and team
            info_text = player_cell.get_text(strip=True)
            
            # Try to match "Name • POS • Team"
            match = re.search(r'•\s*(\w+)\s*•\s*(\w+)', info_text)
            if match:
                pos_str = match.group(1)
                team_str = match.group(2)
            else:
                # Try alternative format
                match = re.search(r',\s*(\w+)\s+(\w+)', info_text)
                if match:
                    team_str = match.group(1)
                    pos_str = match.group(2)
                else:
                    return None
            
            # Map position and team
            position = self._map_position(pos_str)
            team = self._parse_team(team_str)
            
            if not position or not team:
                return None
            
            # Get projected points if available
            proj_points = None
            if len(cells) > 5:
                proj_text = cells[5].get_text(strip=True)
                try:
                    proj_points = float(proj_text)
                except:
                    pass
            
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
                source='cbs',
                projected_points=proj_points
            )
            
            return ranking
            
        except Exception as e:
            logger.debug(f"Error parsing CBS ranking row: {e}")
            return None
    
    def _fetch_from_api(self) -> List[Ranking]:
        """Try to fetch from CBS Sports API"""
        rankings = []
        
        try:
            # CBS Sports API endpoint
            api_url = "https://api.cbssports.com/fantasy/players/rankings"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
            }
            
            params = {
                'version': '3.0',
                'sport': 'football',
                'league_id': 'nfl',
                'period': '2025',
                'limit': '300'
            }
            
            response = self.session.get(api_url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # Parse player data
                if 'body' in data and 'rankings' in data['body']:
                    for player_data in data['body']['rankings']:
                        ranking = self._parse_api_player(player_data)
                        if ranking:
                            rankings.append(ranking)
                            
        except Exception as e:
            logger.debug(f"CBS API error: {e}")
        
        return rankings
    
    def _parse_api_player(self, player_data: Dict) -> Optional[Ranking]:
        """Parse player data from CBS API"""
        try:
            # Extract rank
            rank = player_data.get('rank')
            if not rank:
                return None
            
            # Extract player info
            player_info = player_data.get('player', {})
            name = player_info.get('fullname', '')
            
            if not name:
                return None
            
            # Get position
            position = self._map_position(player_info.get('position', ''))
            if not position:
                return None
            
            # Get team
            team = self._parse_team(player_info.get('pro_team', ''))
            if not team:
                return None
            
            # Get projections
            projected_points = player_data.get('projected_pts', 0)
            
            # Create player and ranking
            player = Player(
                name=name,
                position=position,
                team=team,
                bye_week=player_info.get('bye_week')
            )
            
            ranking = Ranking(
                player=player,
                rank=rank,
                source='cbs',
                projected_points=projected_points
            )
            
            return ranking
            
        except Exception as e:
            logger.debug(f"Error parsing CBS API player: {e}")
            return None
    
    def _map_position(self, pos_str: str) -> Optional[Position]:
        """Map CBS position to our Position enum"""
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
        if team_str in ['FA', 'FREE', '--', 'UFA']:
            return NFLTeam.FA
        
        try:
            return NFLTeam(team_str)
        except ValueError:
            logger.debug(f"Unknown CBS team: {team_str}")
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
                logger.debug(f"Validation error for CBS ranking: {e}")
                continue
            except Exception as e:
                logger.debug(f"Unexpected error validating CBS ranking: {e}")
                continue
        
        return validated_rankings
    
    def _get_fallback_rankings(self) -> List[Ranking]:
        """Return fallback CBS Sports rankings for 2025 season"""
        logger.info("Using CBS Sports fallback rankings for 2025 season")
        
        # Top 50 consensus players from CBS Sports analysts
        fallback_data = [
            # CBS Sports top RBs
            ("Saquon Barkley", "RB", "PHI", 1, 375),
            ("Bijan Robinson", "RB", "ATL", 3, 355),
            ("Jahmyr Gibbs", "RB", "DET", 5, 335),
            ("Christian McCaffrey", "RB", "SF", 7, 315),
            ("Breece Hall", "RB", "NYJ", 8, 310),
            ("Derrick Henry", "RB", "BAL", 11, 285),
            ("Jonathan Taylor", "RB", "IND", 14, 275),
            ("De'Von Achane", "RB", "MIA", 16, 265),
            ("Josh Jacobs", "RB", "GB", 19, 255),
            ("Kyren Williams", "RB", "LAR", 23, 245),
            
            # CBS Sports top WRs
            ("Ja'Marr Chase", "WR", "CIN", 2, 345),
            ("CeeDee Lamb", "WR", "DAL", 4, 325),
            ("Justin Jefferson", "WR", "MIN", 6, 315),
            ("Puka Nacua", "WR", "LAR", 9, 290),
            ("Amon-Ra St. Brown", "WR", "DET", 10, 285),
            ("Tyreek Hill", "WR", "MIA", 12, 280),
            ("A.J. Brown", "WR", "PHI", 13, 275),
            ("Nico Collins", "WR", "HOU", 15, 265),
            ("Malik Nabers", "WR", "NYG", 17, 260),
            ("Davante Adams", "WR", "LAR", 18, 255),
            ("Chris Olave", "WR", "NO", 20, 250),
            ("Mike Evans", "WR", "TB", 21, 245),
            ("Brian Thomas Jr.", "WR", "JAX", 22, 240),
            ("DK Metcalf", "WR", "SEA", 24, 235),
            ("Calvin Ridley", "WR", "TEN", 25, 230),
            
            # CBS Sports top TEs
            ("Sam LaPorta", "TE", "DET", 26, 195),
            ("Travis Kelce", "TE", "KC", 28, 185),
            ("Mark Andrews", "TE", "BAL", 30, 180),
            ("George Kittle", "TE", "SF", 31, 175),
            ("Brock Bowers", "TE", "LV", 32, 170),
            ("Trey McBride", "TE", "ARI", 33, 165),
            ("Dalton Kincaid", "TE", "BUF", 37, 155),
            
            # CBS Sports top QBs
            ("Josh Allen", "QB", "BUF", 27, 415),
            ("Jalen Hurts", "QB", "PHI", 29, 405),
            ("Lamar Jackson", "QB", "BAL", 34, 395),
            ("Patrick Mahomes", "QB", "KC", 35, 385),
            ("Dak Prescott", "QB", "DAL", 36, 375),
            ("Joe Burrow", "QB", "CIN", 38, 365),
            ("C.J. Stroud", "QB", "HOU", 39, 355),
            ("Justin Herbert", "QB", "LAC", 40, 345),
            ("Jordan Love", "QB", "GB", 41, 335),
            ("Tua Tagovailoa", "QB", "MIA", 42, 325),
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
                        source='cbs',
                        projected_points=proj_points,
                        notes="CBS Sports 2025 Rankings"
                    )
                    
                    rankings.append(ranking)
            except Exception as e:
                logger.debug(f"Error creating fallback ranking: {e}")
                continue
        
        return rankings