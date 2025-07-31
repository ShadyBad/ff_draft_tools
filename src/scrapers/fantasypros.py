"""FantasyPros scraper for consensus rankings"""
import json
import logging
import re
from typing import List, Dict, Optional
import time
import requests
from bs4 import BeautifulSoup

from src.scrapers.base import BaseScraper
from src.core.models import Player, Ranking, Position, NFLTeam
from src.utils.validation import InputValidator, ValidationError
from config import RANKING_SOURCES


logger = logging.getLogger(__name__)


class FantasyProsScraper(BaseScraper):
    """Scraper for FantasyPros consensus rankings"""
    
    def __init__(self):
        source_config = RANKING_SOURCES['fantasypros']
        super().__init__('fantasypros', source_config['cache_hours'])
        self.url = source_config['url']
        
        # Team name mappings for FantasyPros
        self.team_mappings = {
            'JAC': 'JAX',  # Jacksonville
            'LA': 'LAR',   # LA Rams (if not specified)
        }
    
    def scrape_rankings(self) -> List[Ranking]:
        """Scrape rankings from FantasyPros"""
        rankings = []
        
        try:
            # Get the main rankings page with retry logic
            soup = self._get_page_with_retry(self.url)
            if not soup:
                logger.warning("Failed to fetch FantasyPros page")
                return []
            
            # Look for the ECR (Expert Consensus Rankings) data
            # FantasyPros often loads data via JavaScript, so we need to find the data script
            scripts = soup.find_all('script')
            
            ecr_data = None
            for script in scripts:
                if script.string and 'ecrData' in script.string:
                    # Extract the JSON data
                    match = re.search(r'var\s+ecrData\s*=\s*({.*?});', script.string, re.DOTALL)
                    if match:
                        try:
                            ecr_data = json.loads(match.group(1))
                            break
                        except json.JSONDecodeError:
                            continue
            
            # Alternative: Look for player data in different format
            if not ecr_data:
                for script in scripts:
                    if script.string and ('players' in script.string or 'rankings' in script.string):
                        # Try to extract player data
                        match = re.search(r'players["\']?\s*:\s*(\[.*?\])', script.string, re.DOTALL)
                        if match:
                            try:
                                players_data = json.loads(match.group(1))
                                rankings = self._parse_players_json(players_data)
                                if rankings:
                                    return rankings
                            except json.JSONDecodeError:
                                continue
            
            # If we found ECR data, parse it
            if ecr_data and 'players' in ecr_data:
                rankings = self._parse_ecr_data(ecr_data['players'])
            else:
                # Fallback: Try to scrape the HTML table directly
                rankings = self._scrape_html_table(soup)
            
            if not rankings:
                logger.info("Could not find rankings data on FantasyPros, using fallback")
                return []
            
            logger.info(f"Scraped {len(rankings)} rankings from FantasyPros")
            
        except Exception as e:
            logger.error(f"Error scraping FantasyPros: {e}")
            return []
        
        # Validate rankings before returning
        return self._validate_rankings(rankings)
    
    def _get_page_with_retry(self, url: str, max_retries: int = 3) -> Optional[BeautifulSoup]:
        """Get page with retry logic for reliability"""
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, timeout=10)
                if response.status_code == 200:
                    return BeautifulSoup(response.content, 'html.parser')
                else:
                    logger.warning(f"FantasyPros returned status {response.status_code}")
            except requests.RequestException as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed to fetch FantasyPros after {max_retries} attempts: {e}")
                else:
                    time.sleep(2 ** attempt)  # Exponential backoff
        return None
    
    def _validate_rankings(self, rankings: List[Ranking]) -> List[Ranking]:
        """Validate all rankings before returning"""
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
                
                # Validate bye week
                if ranking.player.bye_week is not None:
                    ranking.player.bye_week = InputValidator.validate_bye_week(ranking.player.bye_week)
                
                # Validate rank
                if ranking.rank < 1 or ranking.rank > 500:
                    logger.debug(f"Invalid rank {ranking.rank} for {clean_name}")
                    continue
                
                # Validate tier
                if ranking.tier < 1 or ranking.tier > 10:
                    ranking.tier = min(max(ranking.tier, 1), 10)
                
                validated_rankings.append(ranking)
                
            except ValidationError as e:
                logger.debug(f"Validation error for ranking: {e}")
                continue
            except Exception as e:
                logger.debug(f"Unexpected error validating ranking: {e}")
                continue
        
        logger.info(f"Validated {len(validated_rankings)} rankings (removed {len(rankings) - len(validated_rankings)} invalid)")
        return validated_rankings
    
    def _safe_int(self, value: any, default: int = 0) -> int:
        """Safely convert value to int with default"""
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    
    def _parse_ecr_data(self, players_data: List[Dict]) -> List[Ranking]:
        """Parse ECR JSON data"""
        rankings = []
        
        for player_data in players_data:
            try:
                # Extract player info
                player_name = player_data.get('player_name', '')
                if not player_name:
                    continue
                
                # Get position
                pos_str = player_data.get('player_position_id', '')
                position = self._parse_position(pos_str)
                if not position:
                    continue
                
                # Get team
                team_str = player_data.get('player_team_id', '')
                team = self._parse_team(team_str)
                if not team:
                    continue
                
                # Get rank - use safe conversion
                rank = self._safe_int(player_data.get('rank_ecr'))
                if rank == 0:
                    continue
                
                # Get bye week - use safe conversion
                bye_week = self._safe_int(player_data.get('player_bye_week'))
                
                # Get tier if available - use safe conversion
                tier = self._safe_int(player_data.get('tier', 1))
                if tier == 0:
                    tier = 1
                
                # Create player and ranking
                player = Player(
                    name=player_name,
                    position=position,
                    team=team,
                    bye_week=bye_week
                )
                
                ranking = Ranking(
                    player=player,
                    rank=rank,
                    source='fantasypros',
                    tier=tier
                )
                
                rankings.append(ranking)
                
            except Exception as e:
                logger.debug(f"Error parsing player data: {e}")
                continue
        
        return rankings
    
    def _parse_players_json(self, players_data: List[Dict]) -> List[Ranking]:
        """Parse alternative players JSON format"""
        rankings = []
        
        for idx, player_data in enumerate(players_data, 1):
            try:
                # Different field names possible
                player_name = (player_data.get('name') or 
                             player_data.get('player_name') or 
                             player_data.get('full_name', ''))
                
                if not player_name:
                    continue
                
                # Position
                pos_str = (player_data.get('position') or 
                          player_data.get('pos') or 
                          player_data.get('player_position', ''))
                position = self._parse_position(pos_str)
                if not position:
                    continue
                
                # Team
                team_str = (player_data.get('team') or 
                           player_data.get('team_abbr') or 
                           player_data.get('player_team', ''))
                team = self._parse_team(team_str)
                if not team:
                    continue
                
                # Rank
                rank = self._safe_int(player_data.get('rank') or player_data.get('overall_rank') or idx)
                
                # Bye week
                bye_week = self._safe_int(player_data.get('bye') or player_data.get('bye_week'))
                
                # Create player and ranking
                player = Player(
                    name=player_name,
                    position=position,
                    team=team,
                    bye_week=bye_week
                )
                
                ranking = Ranking(
                    player=player,
                    rank=rank,
                    source='fantasypros'
                )
                
                rankings.append(ranking)
                
            except Exception as e:
                logger.debug(f"Error parsing player: {e}")
                continue
        
        return rankings
    
    def _scrape_html_table(self, soup: BeautifulSoup) -> List[Ranking]:
        """Fallback: Scrape rankings from HTML table"""
        rankings = []
        
        # Look for the rankings table
        table = soup.find('table', {'id': ['ranking-table', 'data', 'rankings']})
        if not table:
            # Try to find any table with player data
            tables = soup.find_all('table')
            for t in tables:
                if 'player' in str(t.get('class', [])).lower():
                    table = t
                    break
        
        if not table:
            return rankings
        
        # Parse table rows
        tbody = table.find('tbody')
        if not tbody:
            return rankings
        
        rows = tbody.find_all('tr')
        
        for idx, row in enumerate(rows, 1):
            try:
                cells = row.find_all('td')
                if len(cells) < 3:
                    continue
                
                # Extract rank (usually first cell)
                rank = idx
                rank_text = cells[0].get_text(strip=True)
                if rank_text.isdigit():
                    rank = int(rank_text)
                
                # Extract player name and info
                player_cell = cells[1]  # Usually second cell
                player_name = ''
                
                # Look for player name in various ways
                player_link = player_cell.find('a', class_=['player-name', 'player'])
                if player_link:
                    player_name = player_link.get_text(strip=True)
                else:
                    # Get first text that looks like a name
                    player_text = player_cell.get_text(strip=True)
                    # Remove position and team info if in same cell
                    player_name = re.split(r'[A-Z]{2,3}\s*[-–]', player_text)[0].strip()
                
                if not player_name or len(player_name) < 3:
                    continue
                
                # Extract team and position (often in same cell)
                cell_text = player_cell.get_text(' ', strip=True)
                
                # Common patterns: "Player Name WR - KC" or "Player Name (WR - KC)"
                match = re.search(r'([A-Z]{2,3})\s*[-–]\s*([A-Z]{2,3})', cell_text)
                if match:
                    pos_str = match.group(1)
                    team_str = match.group(2)
                else:
                    # Try other cells
                    pos_str = ''
                    team_str = ''
                    for cell in cells[2:5]:  # Check next few cells
                        text = cell.get_text(strip=True)
                        if text in ['QB', 'RB', 'WR', 'TE', 'K', 'DST', 'DEF']:
                            pos_str = text
                        elif len(text) == 2 or len(text) == 3 and text.isupper():
                            team_str = text
                
                position = self._parse_position(pos_str)
                team = self._parse_team(team_str)
                
                if not position or not team:
                    continue
                
                # Get bye week (usually in its own column)
                bye_week = 0
                for i, cell in enumerate(cells):
                    cell_text = cell.get_text(strip=True)
                    # Look for a number between 4 and 14 (typical bye weeks)
                    if cell_text.isdigit() and 4 <= int(cell_text) <= 14:
                        bye_week = int(cell_text)
                        break
                
                # Create player and ranking
                player = Player(
                    name=player_name,
                    position=position,
                    team=team,
                    bye_week=bye_week
                )
                
                ranking = Ranking(
                    player=player,
                    rank=rank,
                    source='fantasypros'
                )
                
                rankings.append(ranking)
                
            except Exception as e:
                logger.debug(f"Error parsing table row: {e}")
                continue
        
        return rankings
    
    def _parse_position(self, pos_str: str) -> Optional[Position]:
        """Parse position string to Position enum"""
        if not pos_str:
            return None
            
        pos_str = pos_str.upper().strip()
        pos_map = {
            'QB': Position.QB,
            'RB': Position.RB,
            'WR': Position.WR,
            'TE': Position.TE,
            'K': Position.K,
            'PK': Position.K,  # Place Kicker
            'DST': Position.DST,
            'DEF': Position.DST,  # Alternative notation
            'D/ST': Position.DST,
        }
        return pos_map.get(pos_str)
    
    def _parse_team(self, team_str: str) -> Optional[NFLTeam]:
        """Parse team string to NFLTeam enum"""
        if not team_str:
            return None
            
        # Apply mappings
        team_str = self.team_mappings.get(team_str.upper(), team_str.upper())
        
        try:
            return NFLTeam(team_str)
        except ValueError:
            # Handle special cases
            if team_str == 'FA':
                return NFLTeam.FA
            logger.debug(f"Unknown team: {team_str}")
            return None


# Updated fallback data for 2025 season projections
FALLBACK_RANKINGS_2025 = [
    # Top QBs for 2025
    ("Josh Allen", "QB", "BUF", 7, 1, 1),
    ("Lamar Jackson", "QB", "BAL", 8, 2, 1),
    ("Jalen Hurts", "QB", "PHI", 5, 3, 1),
    ("Patrick Mahomes", "QB", "KC", 6, 4, 1),
    ("Dak Prescott", "QB", "DAL", 9, 5, 1),
    ("Joe Burrow", "QB", "CIN", 7, 6, 1),
    ("C.J. Stroud", "QB", "HOU", 5, 7, 1),
    
    # Top RBs for 2025
    ("Bijan Robinson", "RB", "ATL", 8, 8, 1),
    ("Breece Hall", "RB", "NYJ", 6, 9, 1),
    ("Jahmyr Gibbs", "RB", "DET", 9, 10, 1),
    ("Jonathan Taylor", "RB", "IND", 7, 11, 1),
    ("Saquon Barkley", "RB", "PHI", 5, 12, 1),
    ("Christian McCaffrey", "RB", "SF", 10, 13, 1),
    ("De'Von Achane", "RB", "MIA", 6, 14, 1),
    
    # Top WRs for 2025
    ("CeeDee Lamb", "WR", "DAL", 9, 15, 1),
    ("Ja'Marr Chase", "WR", "CIN", 7, 16, 1),
    ("Justin Jefferson", "WR", "MIN", 6, 17, 1),
    ("Amon-Ra St. Brown", "WR", "DET", 9, 18, 1),
    ("Puka Nacua", "WR", "LAR", 8, 19, 1),
    ("A.J. Brown", "WR", "PHI", 5, 20, 1),
    ("Garrett Wilson", "WR", "NYJ", 6, 21, 1),
    ("Chris Olave", "WR", "NO", 11, 22, 1),
    
    # Top TEs for 2025
    ("Sam LaPorta", "TE", "DET", 9, 23, 1),
    ("Trey McBride", "TE", "ARI", 11, 24, 1),
    ("Mark Andrews", "TE", "BAL", 8, 25, 1),
    ("Travis Kelce", "TE", "KC", 6, 26, 2),
    ("Dalton Kincaid", "TE", "BUF", 7, 27, 2),
    ("Brock Bowers", "TE", "LV", 10, 28, 2),
]


def get_fallback_rankings() -> List[Ranking]:
    """Get fallback rankings when scraping fails"""
    rankings = []
    
    for name, pos_str, team_str, bye, overall_rank, tier in FALLBACK_RANKINGS_2025:
        player = Player(
            name=name,
            position=Position(pos_str),
            team=NFLTeam(team_str),
            bye_week=bye
        )
        
        ranking = Ranking(
            player=player,
            rank=overall_rank,
            source='fantasypros',
            tier=tier
        )
        
        rankings.append(ranking)
    
    return rankings