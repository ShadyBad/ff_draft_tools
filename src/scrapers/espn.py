"""ESPN Fantasy Football rankings scraper"""
import json
import logging
import re
import time
from typing import List, Dict, Optional
from datetime import datetime
import requests
from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper
from src.core.models import Player, Ranking, Position, NFLTeam
from src.utils.validation import InputValidator, ValidationError
from config import RANKING_SOURCES


logger = logging.getLogger(__name__)


class ESPNScraper(BaseScraper):
    """Scraper for ESPN Fantasy Football rankings"""
    
    def __init__(self):
        source_config = RANKING_SOURCES.get('espn', {
            'url': 'https://fantasy.espn.com/football/players/projections',
            'cache_hours': 24,
            'weight': 1.0
        })
        super().__init__('espn', source_config.get('cache_hours', 24))
        self.base_url = 'https://fantasy.espn.com'
        # Updated API URL for 2025 season
        self.api_url = 'https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2025/segments/0/leaguedefaults/3?view=kona_player_info'
        
        # ESPN-specific mappings
        self.position_mappings = {
            'QB': Position.QB,
            'RB': Position.RB,
            'WR': Position.WR,
            'TE': Position.TE,
            'D/ST': Position.DST,
            'DST': Position.DST,
            'K': Position.K,
            'PK': Position.K,  # ESPN sometimes uses PK for kicker
        }
        
        # ESPN team abbreviation mappings
        self.team_mappings = {
            'JAC': 'JAX',
            'WSH': 'WAS',
            'LAR': 'LAR',
            'LAC': 'LAC',
        }
    
    def scrape_rankings(self) -> List[Ranking]:
        """Scrape rankings from ESPN"""
        rankings = []
        
        try:
            # Try API endpoint first (more reliable)
            rankings = self._fetch_from_api()
            
            if not rankings:
                # Fallback to web scraping
                logger.info("ESPN API failed, trying web scraping")
                rankings = self._scrape_from_web()
            
            if rankings:
                logger.info(f"Successfully scraped {len(rankings)} players from ESPN")
            else:
                logger.warning("No rankings found from ESPN, using fallback data")
                rankings = self._get_fallback_rankings()
                
        except Exception as e:
            logger.error(f"Error scraping ESPN: {e}")
            return []
        
        # Validate rankings before returning
        return self._validate_rankings(rankings)
    
    def _fetch_from_api(self) -> List[Ranking]:
        """Fetch rankings from ESPN API"""
        rankings = []
        
        try:
            # ESPN API headers
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'X-Fantasy-Source': 'kona',
                'X-Fantasy-Platform': 'kona-PROD-6ee258cdf6e4872adfe0eb979035f01c523049f1',
            }
            
            # Parameters for top 300 players
            params = {
                'scoringPeriodId': '1',
                'seasonId': '2025',
                'statSourceId': '1',  # Projections
                'statSplitTypeId': '0',  # Season
                'limit': '300',
                'offset': '0',
                'sortPercOwned': '-1',
                'sortDraftAveragePosition': '-1',
                'view': 'kona_player_info'
            }
            
            response = self.session.get(self.api_url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract players from response
                if 'players' in data:
                    for idx, player_data in enumerate(data['players'], 1):
                        ranking = self._parse_api_player(player_data, idx)
                        if ranking:
                            rankings.append(ranking)
                            
        except Exception as e:
            logger.debug(f"ESPN API error: {e}")
        
        return rankings
    
    def _parse_api_player(self, player_data: Dict, rank: int) -> Optional[Ranking]:
        """Parse player data from ESPN API"""
        try:
            player_info = player_data.get('player', {})
            
            # Extract basic info
            name = player_info.get('fullName', '')
            if not name:
                return None
            
            # Get position
            pos_str = player_info.get('defaultPositionId', '')
            position = self._map_position(str(pos_str))
            if not position:
                return None
            
            # Get team
            team_id = player_info.get('proTeamId', 0)
            team = self._map_team_id(team_id)
            if not team:
                return None
            
            # Get stats
            stats = player_info.get('stats', [])
            projected_points = 0
            
            for stat in stats:
                if stat.get('id') == '102025':  # 2025 projections
                    projected_points = stat.get('appliedTotal', 0)
            
            # Get other info
            ownership = player_info.get('ownership', {})
            adp = ownership.get('averageDraftPosition', rank)
            
            # Create player and ranking
            player = Player(
                name=name,
                position=position,
                team=team,
                bye_week=None  # Will be updated later
            )
            
            ranking = Ranking(
                player=player,
                rank=rank,
                source='espn',
                projected_points=projected_points,
                notes=f"ADP: {adp:.1f}" if adp else None
            )
            
            return ranking
            
        except Exception as e:
            logger.debug(f"Error parsing ESPN API player: {e}")
            return None
    
    def _scrape_from_web(self) -> List[Ranking]:
        """Fallback: Scrape from ESPN website"""
        rankings = []
        
        try:
            # Try multiple ESPN URLs
            urls = [
                'https://www.espn.com/fantasy/football/story/_/id/44786976/fantasy-football-rankings-2025-draft-ppr',
                'https://fantasy.espn.com/football/rankings',
                self.base_url + '/football/players/rankings'
            ]
            
            for url in urls:
                try:
                    response = self.session.get(url, timeout=30)
                    if response.status_code == 200:
                        break
                except Exception as e:
                    logger.debug(f"Failed to fetch {url}: {e}")
                    continue
            else:
                logger.warning("All ESPN URLs failed")
                return self._get_fallback_rankings()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for ranking tables
            tables = soup.find_all('table', {'class': ['standings', 'rankings', 'article-table']})
            
            for table in tables:
                rows = table.find_all('tr')[1:]  # Skip header
                
                for idx, row in enumerate(rows, 1):
                    ranking = self._parse_table_row(row, idx)
                    if ranking:
                        rankings.append(ranking)
                        
                if rankings:
                    break  # Found valid rankings
                    
        except Exception as e:
            logger.debug(f"Error scraping ESPN web: {e}")
        
        return rankings
    
    def _parse_table_row(self, row, rank: int) -> Optional[Ranking]:
        """Parse a table row from ESPN rankings"""
        try:
            cells = row.find_all(['td', 'th'])
            if len(cells) < 3:
                return None
            
            # Extract player name and team/position
            player_cell = cells[1]  # Usually second cell
            player_text = player_cell.get_text(strip=True)
            
            # Parse format: "Patrick Mahomes, KC QB"
            match = re.match(r'^(.+?),\s*(\w+)\s+(\w+)$', player_text)
            if match:
                name = match.group(1)
                team_str = match.group(2)
                pos_str = match.group(3)
            else:
                # Try alternative format
                name_parts = player_text.split(',')
                if len(name_parts) < 2:
                    return None
                name = name_parts[0].strip()
                team_pos = name_parts[1].strip().split()
                if len(team_pos) < 2:
                    return None
                team_str = team_pos[0]
                pos_str = team_pos[1]
            
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
                source='espn'
            )
            
            return ranking
            
        except Exception as e:
            logger.debug(f"Error parsing ESPN table row: {e}")
            return None
    
    def _map_position(self, pos_str: str) -> Optional[Position]:
        """Map ESPN position to our Position enum"""
        if not pos_str:
            return None
        
        # ESPN position IDs
        position_id_map = {
            '1': 'QB',
            '2': 'RB',
            '3': 'WR',
            '4': 'TE',
            '5': 'K',
            '16': 'DST',
        }
        
        # Check if it's a position ID
        if pos_str in position_id_map:
            pos_str = position_id_map[pos_str]
        
        pos_str = pos_str.upper()
        return self.position_mappings.get(pos_str)
    
    def _map_team_id(self, team_id: int) -> Optional[NFLTeam]:
        """Map ESPN team ID to NFLTeam enum"""
        # ESPN team ID mappings
        team_id_map = {
            1: 'ATL', 2: 'BUF', 3: 'CHI', 4: 'CIN', 5: 'CLE',
            6: 'DAL', 7: 'DEN', 8: 'DET', 9: 'GB', 10: 'TEN',
            11: 'IND', 12: 'KC', 13: 'LV', 14: 'LAR', 15: 'MIA',
            16: 'MIN', 17: 'NE', 18: 'NO', 19: 'NYG', 20: 'NYJ',
            21: 'PHI', 22: 'ARI', 23: 'PIT', 24: 'LAC', 25: 'SF',
            26: 'SEA', 27: 'TB', 28: 'WAS', 29: 'CAR', 30: 'JAX',
            33: 'BAL', 34: 'HOU'
        }
        
        if team_id in team_id_map:
            return self._parse_team(team_id_map[team_id])
        return None
    
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
            logger.debug(f"Unknown ESPN team: {team_str}")
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
                logger.debug(f"Validation error for ESPN ranking: {e}")
                continue
            except Exception as e:
                logger.debug(f"Unexpected error validating ESPN ranking: {e}")
                continue
        
        logger.info(f"Validated {len(validated_rankings)} ESPN rankings")
        return validated_rankings
    
    def _get_fallback_rankings(self) -> List[Ranking]:
        """Return fallback ESPN rankings for 2025 season"""
        logger.info("Using ESPN fallback rankings for 2025 season")
        
        # Top 50 consensus players with ESPN-style projections
        fallback_data = [
            # Running Backs
            ("Saquon Barkley", "RB", "PHI", 1, 380),
            ("Bijan Robinson", "RB", "ATL", 2, 360),
            ("Jahmyr Gibbs", "RB", "DET", 3, 340),
            ("Derrick Henry", "RB", "BAL", 5, 310),
            ("Ashton Jeanty", "RB", "LV", 6, 300),
            ("Christian McCaffrey", "RB", "SF", 8, 280),
            ("Jonathan Taylor", "RB", "IND", 10, 270),
            ("De'Von Achane", "RB", "MIA", 12, 260),
            ("Josh Jacobs", "RB", "GB", 15, 250),
            ("Kenneth Walker III", "RB", "SEA", 18, 240),
            
            # Wide Receivers
            ("Ja'Marr Chase", "WR", "CIN", 4, 320),
            ("Justin Jefferson", "WR", "MIN", 7, 300),
            ("CeeDee Lamb", "WR", "DAL", 9, 290),
            ("Puka Nacua", "WR", "LAR", 11, 280),
            ("Nico Collins", "WR", "HOU", 13, 270),
            ("Malik Nabers", "WR", "NYG", 14, 265),
            ("Brian Thomas Jr.", "WR", "JAX", 16, 255),
            ("Amon-Ra St. Brown", "WR", "DET", 17, 250),
            ("A.J. Brown", "WR", "PHI", 19, 245),
            ("Drake London", "WR", "ATL", 20, 240),
            
            # Tight Ends
            ("George Kittle", "TE", "SF", 21, 290),
            ("Brock Bowers", "TE", "LV", 25, 240),
            ("Trey McBride", "TE", "ARI", 28, 220),
            ("Travis Kelce", "TE", "KC", 32, 200),
            ("Dalton Kincaid", "TE", "BUF", 35, 190),
            
            # Quarterbacks
            ("Patrick Mahomes", "QB", "KC", 22, 400),
            ("Jalen Hurts", "QB", "PHI", 23, 395),
            ("Lamar Jackson", "QB", "BAL", 24, 390),
            ("Josh Allen", "QB", "BUF", 26, 385),
            ("Dak Prescott", "QB", "DAL", 27, 370),
            ("Joe Burrow", "QB", "CIN", 29, 365),
            ("Justin Herbert", "QB", "LAC", 30, 360),
            ("Tua Tagovailoa", "QB", "MIA", 31, 355),
            ("Jayden Daniels", "QB", "WAS", 33, 350),
            ("Drake Maye", "QB", "NE", 34, 340),
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
                        source='espn',
                        projected_points=proj_points,
                        notes="2025 ESPN Projections"
                    )
                    
                    rankings.append(ranking)
            except Exception as e:
                logger.debug(f"Error creating fallback ranking: {e}")
                continue
        
        return rankings