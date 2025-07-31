"""Fantasy point projections for players"""
import logging
from typing import List, Dict, Optional
from collections import defaultdict

from src.core.models import Position, ConsensusRanking
from config import SCORING_SYSTEMS, DEFAULT_SETTINGS


logger = logging.getLogger(__name__)


class ProjectionCalculator:
    """Calculate fantasy point projections based on historical data and rankings"""
    
    def __init__(self, scoring_system: str = None):
        self.scoring_system = scoring_system or DEFAULT_SETTINGS.get("scoring", "HALF_PPR")
        self.scoring = SCORING_SYSTEMS.get(self.scoring_system, SCORING_SYSTEMS["HALF_PPR"])
    
    def add_projections(self, rankings: List[ConsensusRanking]) -> List[ConsensusRanking]:
        """
        Add projected fantasy points to rankings based on historical averages
        
        This is a simplified projection system based on ADP/rank.
        In a full implementation, this would use advanced statistical models.
        """
        # Historical fantasy points by rank for 2024 season (Half-PPR)
        # These serve as baseline projections
        rank_to_points = {
            Position.QB: {
                1: 380, 2: 365, 3: 350, 4: 340, 5: 330, 6: 320, 7: 310, 8: 300,
                9: 290, 10: 280, 11: 270, 12: 260, 13: 250, 14: 240, 15: 230,
                16: 220, 17: 210, 18: 200, 19: 190, 20: 180
            },
            Position.RB: {
                1: 350, 2: 320, 3: 300, 4: 280, 5: 265, 6: 250, 7: 240, 8: 230,
                9: 220, 10: 210, 11: 200, 12: 190, 13: 180, 14: 170, 15: 165,
                16: 160, 17: 155, 18: 150, 19: 145, 20: 140, 21: 135, 22: 130,
                23: 125, 24: 120, 25: 115, 26: 110, 27: 105, 28: 100, 29: 95,
                30: 90, 31: 85, 32: 80, 33: 75, 34: 70, 35: 65, 36: 60
            },
            Position.WR: {
                1: 340, 2: 320, 3: 300, 4: 285, 5: 270, 6: 260, 7: 250, 8: 240,
                9: 230, 10: 220, 11: 210, 12: 200, 13: 195, 14: 190, 15: 185,
                16: 180, 17: 175, 18: 170, 19: 165, 20: 160, 21: 155, 22: 150,
                23: 145, 24: 140, 25: 135, 26: 130, 27: 125, 28: 120, 29: 115,
                30: 110, 31: 105, 32: 100, 33: 95, 34: 90, 35: 85, 36: 80
            },
            Position.TE: {
                1: 280, 2: 240, 3: 210, 4: 190, 5: 170, 6: 155, 7: 145, 8: 135,
                9: 125, 10: 115, 11: 105, 12: 95, 13: 85, 14: 75, 15: 70,
                16: 65, 17: 60, 18: 55, 19: 50, 20: 45
            },
            Position.K: {
                1: 150, 2: 145, 3: 142, 4: 140, 5: 138, 6: 136, 7: 134, 8: 132,
                9: 130, 10: 128, 11: 126, 12: 124, 13: 122, 14: 120, 15: 118,
                16: 116, 17: 114, 18: 112, 19: 110, 20: 108
            },
            Position.DST: {
                1: 160, 2: 150, 3: 145, 4: 140, 5: 135, 6: 130, 7: 125, 8: 120,
                9: 115, 10: 110, 11: 105, 12: 100, 13: 95, 14: 90, 15: 85,
                16: 80, 17: 75, 18: 70, 19: 65, 20: 60
            }
        }
        
        # Scoring system adjustments
        scoring_adjustments = {
            "STANDARD": {
                Position.RB: 0.95,   # RBs slightly less valuable
                Position.WR: 0.90,   # WRs significantly less valuable
                Position.TE: 0.85,   # TEs less valuable
            },
            "PPR": {
                Position.RB: 1.05,   # RBs slightly more valuable
                Position.WR: 1.15,   # WRs significantly more valuable
                Position.TE: 1.20,   # TEs more valuable
            },
            "HALF_PPR": {
                # Baseline, no adjustment
            }
        }
        
        # Group by position to assign position-based projections
        by_position = defaultdict(list)
        for ranking in rankings:
            by_position[ranking.player.position].append(ranking)
        
        # Sort each position by consensus rank
        for position in by_position:
            by_position[position].sort(key=lambda x: x.consensus_rank)
        
        # Assign projections based on position rank
        for position, position_rankings in by_position.items():
            position_projections = rank_to_points.get(position, {})
            
            for i, ranking in enumerate(position_rankings, 1):
                # Get base projection for this rank
                if i in position_projections:
                    base_points = position_projections[i]
                else:
                    # Extrapolate for ranks beyond our data
                    if position_projections:
                        last_rank = max(position_projections.keys())
                        last_points = position_projections[last_rank]
                        # Decrease by 5 points per rank beyond last
                        base_points = max(20, last_points - (i - last_rank) * 5)
                    else:
                        base_points = 100  # Default fallback
                
                # Apply scoring system adjustment
                adjustment = 1.0
                if self.scoring_system in scoring_adjustments:
                    adjustment = scoring_adjustments[self.scoring_system].get(position, 1.0)
                
                # Set projected points
                ranking.projected_points = base_points * adjustment
        
        return rankings
    
    def calculate_projections_from_stats(self, player_stats: Dict) -> float:
        """
        Calculate fantasy points from raw statistics
        
        Args:
            player_stats: Dictionary of player statistics
            
        Returns:
            Projected fantasy points
        """
        points = 0.0
        
        # Passing
        points += player_stats.get('pass_yds', 0) * self.scoring.get('pass_yds', 0)
        points += player_stats.get('pass_td', 0) * self.scoring.get('pass_td', 0)
        points += player_stats.get('pass_int', 0) * self.scoring.get('pass_int', 0)
        
        # Rushing
        points += player_stats.get('rush_yds', 0) * self.scoring.get('rush_yds', 0)
        points += player_stats.get('rush_td', 0) * self.scoring.get('rush_td', 0)
        
        # Receiving
        points += player_stats.get('rec_yds', 0) * self.scoring.get('rec_yds', 0)
        points += player_stats.get('rec_td', 0) * self.scoring.get('rec_td', 0)
        points += player_stats.get('receptions', 0) * self.scoring.get('receptions', 0)
        
        # Misc
        points += player_stats.get('fumbles_lost', 0) * self.scoring.get('fumble', 0)
        
        return points