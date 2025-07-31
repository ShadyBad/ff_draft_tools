"""Value-Based Drafting (VBD) implementation with VORP calculations"""
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from src.core.models import Position, ConsensusRanking
from config import DEFAULT_SETTINGS


logger = logging.getLogger(__name__)


class VBDBaseline(Enum):
    """Different baseline methodologies for VBD"""
    VOLS = "vols"  # Value Over Last Starter
    VORP = "vorp"  # Value Over Replacement Player (Waiver Wire)
    BEER = "beer"  # Best Ever Evaluation of Replacement (Man-Games)


@dataclass
class VORPResult:
    """Result of VORP calculation for a player"""
    player_name: str
    position: Position
    projected_points: float
    baseline_points: float
    vorp_score: float
    baseline_type: VBDBaseline
    baseline_player: Optional[str] = None
    
    @property
    def value_added(self) -> float:
        """Alias for vorp_score"""
        return self.vorp_score


class VBDCalculator:
    """Calculate Value Over Replacement Player (VORP) for rankings"""
    
    def __init__(self, league_settings: Optional[Dict] = None):
        self.settings = league_settings or DEFAULT_SETTINGS
        self.num_teams = self.settings.get("teams", 12)
        self.roster = self.settings.get("roster", DEFAULT_SETTINGS["roster"])
        
        # Add aliases for compatibility
        self.teams = self.num_teams
        self.roster_slots = self.roster
        self.flex_positions = {Position.RB, Position.WR, Position.TE}
        
        # Cache for baseline calculations
        self._baseline_cache = {}
    
    def calculate_vorp(self, 
                      rankings: List[ConsensusRanking], 
                      baseline_type: VBDBaseline = VBDBaseline.VORP) -> List[VORPResult]:
        """
        Calculate VORP for all players using specified baseline methodology
        
        Args:
            rankings: List of consensus rankings with projections
            baseline_type: Which VBD baseline methodology to use
            
        Returns:
            List of VORP results sorted by value
        """
        # First, ensure all players have projected points
        players_with_projections = [
            r for r in rankings 
            if hasattr(r, 'projected_points') and r.projected_points is not None
        ]
        
        if not players_with_projections:
            logger.warning("No players have projected points. VORP calculation requires projections.")
            return []
        
        # Calculate baselines for each position
        baselines = self._calculate_baselines(players_with_projections, baseline_type)
        
        # Calculate VORP for each player
        vorp_results = []
        for ranking in players_with_projections:
            position = ranking.player.position
            if position not in baselines:
                continue
                
            baseline_points, baseline_player = baselines[position]
            vorp_score = ranking.projected_points - baseline_points
            
            result = VORPResult(
                player_name=ranking.player.name,
                position=position,
                projected_points=ranking.projected_points,
                baseline_points=baseline_points,
                vorp_score=max(0, vorp_score),  # VORP shouldn't be negative
                baseline_type=baseline_type,
                baseline_player=baseline_player
            )
            vorp_results.append(result)
        
        # Sort by VORP score descending
        vorp_results.sort(key=lambda x: x.vorp_score, reverse=True)
        
        return vorp_results
    
    def _calculate_baselines(self, 
                           rankings: List[ConsensusRanking], 
                           baseline_type: VBDBaseline) -> Dict[Position, Tuple[float, str]]:
        """
        Calculate baseline points for each position based on methodology
        
        Returns:
            Dict mapping Position to (baseline_points, baseline_player_name)
        """
        # Group rankings by position
        by_position = defaultdict(list)
        for ranking in rankings:
            by_position[ranking.player.position].append(ranking)
        
        # Sort each position by projected points descending
        for position in by_position:
            by_position[position].sort(key=lambda x: x.projected_points, reverse=True)
        
        baselines = {}
        
        if baseline_type == VBDBaseline.VOLS:
            baselines = self._calculate_vols_baselines(by_position)
        elif baseline_type == VBDBaseline.VORP:
            baselines = self._calculate_vorp_baselines(by_position)
        elif baseline_type == VBDBaseline.BEER:
            baselines = self._calculate_beer_baselines(by_position)
        
        return baselines
    
    def _calculate_vols_baselines(self, by_position: Dict[Position, List[ConsensusRanking]]) -> Dict[Position, Tuple[float, str]]:
        """
        VOLS: Value Over Last Starter
        Baseline = worst starting player at each position
        """
        baselines = {}
        
        for position, players in by_position.items():
            if position == Position.FLEX:
                continue  # FLEX handled separately
                
            # Number of starters at this position across all teams
            starters_needed = self.roster.get(position.value, 0) * self.num_teams
            
            if starters_needed > 0 and len(players) >= starters_needed:
                # Baseline is the last starter
                baseline_idx = starters_needed - 1
                baseline_player = players[baseline_idx]
                baselines[position] = (
                    baseline_player.projected_points,
                    baseline_player.player.name
                )
            else:
                # Not enough players, use last available
                if players:
                    baseline_player = players[-1]
                    baselines[position] = (
                        baseline_player.projected_points,
                        baseline_player.player.name
                    )
                else:
                    baselines[position] = (0, "None")
        
        return baselines
    
    def _calculate_vorp_baselines(self, by_position: Dict[Position, List[ConsensusRanking]]) -> Dict[Position, Tuple[float, str]]:
        """
        VORP: Value Over Replacement Player (Best Waiver Wire Player)
        Baseline = best player expected to be on waivers after draft
        """
        baselines = {}
        
        # Estimate how many players at each position will be drafted
        draft_multipliers = {
            Position.QB: 1.5,  # Teams draft ~1.5 QBs
            Position.RB: 3.5,  # Teams draft ~3.5 RBs
            Position.WR: 4.0,  # Teams draft ~4 WRs
            Position.TE: 1.5,  # Teams draft ~1.5 TEs
            Position.K: 1.0,   # Teams draft 1 K
            Position.DST: 1.0  # Teams draft 1 DST
        }
        
        for position, players in by_position.items():
            if position == Position.FLEX:
                continue
                
            multiplier = draft_multipliers.get(position, 2.0)
            players_drafted = int(self.num_teams * multiplier)
            
            if len(players) > players_drafted:
                # Baseline is first undrafted player
                baseline_player = players[players_drafted]
                baselines[position] = (
                    baseline_player.projected_points,
                    baseline_player.player.name
                )
            else:
                # Not enough players, use last available
                if players:
                    baseline_player = players[-1]
                    baselines[position] = (
                        baseline_player.projected_points,
                        baseline_player.player.name
                    )
                else:
                    baselines[position] = (0, "None")
        
        return baselines
    
    def _calculate_beer_baselines(self, by_position: Dict[Position, List[ConsensusRanking]]) -> Dict[Position, Tuple[float, str]]:
        """
        BEER: Best Ever Evaluation of Replacement
        Accounts for bye weeks and injury rates to determine man-games needed
        """
        baselines = {}
        
        # Man-games needed accounting for byes and typical injury rates
        # These account for 17-game season + bye week + injury buffer
        man_games_multipliers = {
            Position.QB: 1.2,   # Low injury rate
            Position.RB: 2.5,   # High injury rate
            Position.WR: 2.0,   # Moderate injury rate
            Position.TE: 1.5,   # Low-moderate injury rate
            Position.K: 1.1,    # Very low injury rate
            Position.DST: 1.1   # Very low "injury" rate
        }
        
        for position, players in by_position.items():
            if position == Position.FLEX:
                continue
                
            starters_needed = self.roster.get(position.value, 0) * self.num_teams
            multiplier = man_games_multipliers.get(position, 1.5)
            
            # Total "man-games" needed across the league
            total_needed = int(starters_needed * multiplier)
            
            if len(players) >= total_needed:
                baseline_player = players[total_needed - 1]
                baselines[position] = (
                    baseline_player.projected_points,
                    baseline_player.player.name
                )
            else:
                # Not enough players, use last available
                if players:
                    baseline_player = players[-1]
                    baselines[position] = (
                        baseline_player.projected_points,
                        baseline_player.player.name
                    )
                else:
                    baselines[position] = (0, "None")
        
        return baselines
    
    def get_positional_scarcity(self, vorp_results: List[VORPResult]) -> Dict[Position, float]:
        """
        Calculate positional scarcity based on VORP drop-offs
        Higher score = more scarce/valuable position
        """
        scarcity = {}
        
        # Group by position
        by_position = defaultdict(list)
        for result in vorp_results:
            by_position[result.position].append(result)
        
        for position, results in by_position.items():
            if len(results) < 2:
                scarcity[position] = 0.0
                continue
            
            # Calculate the drop-off rate in VORP
            # Higher drop-off = more scarce
            top_vorp = results[0].vorp_score
            
            # Look at drop-off to player at 2x starter requirement
            starters_needed = self.roster.get(position.value, 0) * self.num_teams
            check_idx = min(starters_needed * 2, len(results) - 1)
            
            if check_idx > 0:
                later_vorp = results[check_idx].vorp_score
                drop_off = top_vorp - later_vorp
                
                # Normalize by top VORP to get percentage drop-off
                if top_vorp > 0:
                    scarcity[position] = drop_off / top_vorp
                else:
                    scarcity[position] = 0.0
            else:
                scarcity[position] = 0.0
        
        return scarcity
    
    def create_draft_board(self, 
                          rankings: List[ConsensusRanking], 
                          baseline_type: VBDBaseline = VBDBaseline.VORP) -> List[ConsensusRanking]:
        """
        Create a draft board by calculating VORP and reordering rankings
        
        Returns:
            Rankings sorted by VORP score
        """
        # Calculate VORP
        vorp_results = self.calculate_vorp(rankings, baseline_type)
        
        # Create lookup dictionary
        vorp_lookup = {r.player_name: r for r in vorp_results}
        
        # Add VORP scores to rankings and sort
        for ranking in rankings:
            if ranking.player.name in vorp_lookup:
                ranking.vorp = vorp_lookup[ranking.player.name].vorp_score
            else:
                ranking.vorp = 0.0
        
        # Sort by VORP descending
        rankings.sort(key=lambda x: getattr(x, 'vorp', 0), reverse=True)
        
        return rankings