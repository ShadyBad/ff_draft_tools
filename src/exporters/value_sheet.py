"""Value sheet exporter for simplified draft rankings"""
import logging
from pathlib import Path
from typing import List, Dict, Optional
from collections import defaultdict

from src.core.models import ConsensusRanking, Position
from config import OUTPUT_DIR


logger = logging.getLogger(__name__)


class ValueSheetExporter:
    """Export rankings in a simplified value-based format"""
    
    def __init__(self):
        self.output_dir = OUTPUT_DIR / 'latest'
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def export_value_sheet(self, rankings: List[ConsensusRanking], 
                          baseline_type: str = "positional") -> Path:
        """Export rankings in value sheet format"""
        
        # Group by position
        by_position = defaultdict(list)
        for ranking in rankings:
            by_position[ranking.player.position].append(ranking)
        
        # Sort each position by VORP (or consensus rank if no VORP)
        for position in by_position:
            by_position[position].sort(
                key=lambda x: getattr(x, 'vorp', 0) or -x.consensus_rank, 
                reverse=True
            )
        
        # Create the value sheet
        output_path = self.output_dir / 'value_sheet.txt'
        
        with open(output_path, 'w') as f:
            # Write each position section
            for position in [Position.QB, Position.RB, Position.WR, Position.TE]:
                if position not in by_position:
                    continue
                
                # Write position header
                position_name = self._get_position_name(position)
                f.write(f"{position_name}\n")
                f.write("VALUE    TM    NAME    PTS/WK    #\n")
                
                # Calculate baseline for this position
                position_rankings = by_position[position]
                baseline_pts = self._calculate_baseline(position, position_rankings)
                
                # Write players
                for i, ranking in enumerate(position_rankings[:self._get_position_limit(position)], 1):
                    # Calculate points above/below baseline
                    player_pts = ranking.projected_points if ranking.projected_points else 0
                    weekly_pts = player_pts / 17  # Convert to weekly
                    pts_diff = weekly_pts - baseline_pts
                    
                    # Format the line
                    value = int(getattr(ranking, 'vorp', 0)) if hasattr(ranking, 'vorp') else ""
                    team = ranking.player.team.value
                    name = ranking.player.name
                    pts_str = f"{pts_diff:+.1f}"
                    
                    # Write the line with proper spacing
                    if value:
                        line = f"{value:<8}{team:<6}{name:<25}{pts_str:<10}{i}\n"
                    else:
                        line = f"{team:<14}{name:<25}{pts_str:<10}{i}\n"
                    
                    f.write(line)
                
                f.write("\n")  # Empty line between positions
        
        logger.info(f"Exported value sheet to {output_path}")
        return output_path
    
    def _get_position_name(self, position: Position) -> str:
        """Get display name for position"""
        position_names = {
            Position.QB: "QUARTERBACK",
            Position.RB: "RUNNING BACK",
            Position.WR: "WIDE RECEIVER",
            Position.TE: "TIGHT END",
            Position.K: "KICKER",
            Position.DST: "DEFENSE"
        }
        return position_names.get(position, position.value)
    
    def _get_position_limit(self, position: Position) -> int:
        """Get how many players to show for each position"""
        limits = {
            Position.QB: 20,
            Position.RB: 40,
            Position.WR: 60,
            Position.TE: 10,
            Position.K: 15,
            Position.DST: 15
        }
        return limits.get(position, 20)
    
    def _calculate_baseline(self, position: Position, rankings: List[ConsensusRanking]) -> float:
        """Calculate baseline points for a position"""
        # Use replacement level baseline (similar to your example)
        baseline_indices = {
            Position.QB: 12,  # QB12 is baseline
            Position.RB: 24,  # RB24 is baseline
            Position.WR: 36,  # WR36 is baseline
            Position.TE: 10,  # TE10 is baseline
            Position.K: 12,
            Position.DST: 12
        }
        
        baseline_idx = baseline_indices.get(position, 12) - 1  # 0-based
        
        if len(rankings) > baseline_idx:
            baseline_player = rankings[baseline_idx]
            if baseline_player.projected_points:
                return baseline_player.projected_points / 17  # Weekly
        
        return 10.0  # Default baseline if not enough players