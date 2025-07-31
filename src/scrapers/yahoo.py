"""Yahoo Fantasy Football rankings scraper"""
import logging
import re
from typing import List, Optional

from src.scrapers.base import BaseScraper
from src.core.models import Player, Ranking, Position, NFLTeam


logger = logging.getLogger(__name__)


class YahooScraper(BaseScraper):
    """Scraper for Yahoo Fantasy Football rankings"""
    
    def __init__(self):
        super().__init__('yahoo', cache_hours=12)
        # Yahoo's draft analysis page has public rankings
        self.url = "https://football.fantasysports.yahoo.com/f1/draftanalysis"
        
        # Team mappings specific to Yahoo
        self.team_mappings = {
            'JAC': 'JAX',
            'WSH': 'WAS',
        }
    
    def scrape_rankings(self) -> List[Ranking]:
        """Scrape rankings from Yahoo Fantasy Football"""
        rankings = []
        
        try:
            # Get the draft analysis page
            soup = self._get_page(self.url)
            
            # Yahoo loads rankings dynamically, but sometimes includes initial data
            # Look for player rows in the rankings table
            player_rows = soup.find_all('tr', class_=['Table__TR', 'player-row'])
            
            if not player_rows:
                # Try alternative selectors
                table = soup.find('table', class_=['Table', 'rankings-table'])
                if table:
                    tbody = table.find('tbody')
                    if tbody:
                        player_rows = tbody.find_all('tr')
            
            if player_rows:
                rankings = self._parse_player_rows(player_rows)
            else:
                # Try to find JSON data in scripts
                rankings = self._parse_json_data(soup)
            
            if not rankings:
                logger.warning("Could not find rankings data on Yahoo")
                return []
            
            logger.info(f"Scraped {len(rankings)} rankings from Yahoo")
            
        except Exception as e:
            logger.error(f"Error scraping Yahoo: {e}")
            return []
        
        return rankings
    
    def _parse_player_rows(self, rows) -> List[Ranking]:
        """Parse player rows from HTML table"""
        rankings = []
        
        for idx, row in enumerate(rows, 1):
            try:
                cells = row.find_all('td')
                if len(cells) < 3:
                    continue
                
                # Extract rank
                rank = idx
                rank_cell = cells[0]
                rank_text = rank_cell.get_text(strip=True)
                if rank_text.isdigit():
                    rank = int(rank_text)
                
                # Extract player info
                player_cell = None
                for cell in cells:
                    if cell.find('a', class_=['player-name', 'name']) or 'player' in cell.get('class', []):
                        player_cell = cell
                        break
                
                if not player_cell:
                    player_cell = cells[1]
                
                # Get player name
                player_name = ''
                player_link = player_cell.find('a')
                if player_link:
                    player_name = player_link.get_text(strip=True)
                else:
                    player_name = player_cell.get_text(strip=True).split('\n')[0]
                
                if not player_name:
                    continue
                
                # Extract team and position
                info_text = player_cell.get_text(' ', strip=True)
                
                # Yahoo format: "Player Name - Team POS"
                match = re.search(r'-\s*([A-Z]{2,3})\s+([A-Z]{1,3})', info_text)
                if match:
                    team_str = match.group(1)
                    pos_str = match.group(2)
                else:
                    # Alternative format
                    pos_str = ''
                    team_str = ''
                    
                    # Look for position abbreviations
                    pos_match = re.search(r'\b(QB|RB|WR|TE|K|DEF)\b', info_text)
                    if pos_match:
                        pos_str = pos_match.group(1)
                    
                    # Look for team abbreviations
                    team_match = re.search(r'\b([A-Z]{2,3})\b', info_text.replace(pos_str, ''))
                    if team_match:
                        team_str = team_match.group(1)
                
                position = self._parse_position(pos_str)
                team = self._parse_team(team_str)
                
                if not position or not team:
                    continue
                
                # Get bye week
                bye_week = self._extract_bye_week(cells)
                
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
                    source='yahoo'
                )
                
                rankings.append(ranking)
                
            except Exception as e:
                logger.debug(f"Error parsing Yahoo player row: {e}")
                continue
        
        return rankings
    
    def _parse_json_data(self, soup) -> List[Ranking]:
        """Try to extract rankings from JavaScript data"""
        rankings = []
        
        scripts = soup.find_all('script')
        for script in scripts:
            if not script.string:
                continue
            
            # Look for player data patterns
            if 'players' in script.string or 'rankings' in script.string:
                # Try to extract JSON-like data
                matches = re.findall(r'\{[^{}]*"name"[^{}]*"position"[^{}]*\}', script.string)
                
                for match in matches:
                    try:
                        # Clean up the match to make it valid JSON
                        json_str = match.replace("'", '"')
                        import json
                        player_data = json.loads(json_str)
                        
                        player_name = player_data.get('name', '')
                        if not player_name:
                            continue
                        
                        pos_str = player_data.get('position', '')
                        team_str = player_data.get('team', '')
                        
                        position = self._parse_position(pos_str)
                        team = self._parse_team(team_str)
                        
                        if position and team:
                            player = Player(
                                name=player_name,
                                position=position,
                                team=team,
                                bye_week=player_data.get('bye', 0)
                            )
                            
                            ranking = Ranking(
                                player=player,
                                rank=player_data.get('rank', len(rankings) + 1),
                                source='yahoo'
                            )
                            
                            rankings.append(ranking)
                    
                    except Exception:
                        continue
        
        return rankings
    
    def _parse_position(self, pos_str: str) -> Optional[Position]:
        """Parse position string"""
        if not pos_str:
            return None
        
        pos_str = pos_str.upper().strip()
        pos_map = {
            'QB': Position.QB,
            'RB': Position.RB,
            'WR': Position.WR,
            'TE': Position.TE,
            'K': Position.K,
            'DEF': Position.DST,
            'DST': Position.DST,
        }
        return pos_map.get(pos_str)
    
    def _parse_team(self, team_str: str) -> Optional[NFLTeam]:
        """Parse team string"""
        if not team_str:
            return None
        
        team_str = team_str.upper().strip()
        team_str = self.team_mappings.get(team_str, team_str)
        
        try:
            return NFLTeam(team_str)
        except ValueError:
            logger.warning(f"Unknown Yahoo team: {team_str}")
            return None
    
    def _extract_bye_week(self, cells) -> int:
        """Extract bye week from row cells"""
        for cell in cells:
            text = cell.get_text(strip=True)
            if text.isdigit() and 1 <= int(text) <= 14:
                # Likely a bye week
                return int(text)
        return 0