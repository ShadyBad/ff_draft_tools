"""Ranking aggregation logic"""
import logging
import statistics
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

from src.core.models import Player, Ranking, ConsensusRanking, Position
from src.core.normalizer import PlayerNormalizer
from src.core.projections import ProjectionCalculator
from src.core.vbd import VBDCalculator, VBDBaseline
from src.utils.validation import InputValidator, ValidationError
from src.utils.monitoring import monitor, measure_performance
from config import RANKING_SOURCES, DEFAULT_TIER_SIZES, DEFAULT_SETTINGS


logger = logging.getLogger(__name__)


class RankingAggregator:
    """Aggregates rankings from multiple sources into consensus rankings"""
    
    def __init__(self, league_settings: Optional[Dict] = None):
        self.normalizer = PlayerNormalizer()
        self.source_weights = {
            source: config['weight'] 
            for source, config in RANKING_SOURCES.items()
        }
        self.settings = league_settings or DEFAULT_SETTINGS
        self.projection_calculator = ProjectionCalculator(self.settings.get("scoring"))
        self.vbd_calculator = VBDCalculator(self.settings)
    
    @measure_performance("aggregate_rankings")
    def aggregate_rankings(self, source_rankings: Dict[str, List[Ranking]], 
                         use_vbd: bool = False,
                         vbd_baseline: VBDBaseline = VBDBaseline.VORP) -> List[ConsensusRanking]:
        """Aggregate rankings from multiple sources into consensus rankings"""
        
        # Validate input rankings
        validated_rankings = {}
        for source, rankings in source_rankings.items():
            if not isinstance(rankings, list):
                logger.warning(f"Skipping invalid rankings from {source}")
                continue
            
            # Filter out invalid rankings
            valid_rankings = []
            for ranking in rankings:
                try:
                    # Basic validation
                    if not hasattr(ranking, 'player') or not hasattr(ranking, 'rank'):
                        continue
                    
                    if ranking.rank < 1 or ranking.rank > 500:
                        continue
                        
                    valid_rankings.append(ranking)
                except Exception as e:
                    logger.debug(f"Skipping invalid ranking: {e}")
                    continue
            
            if valid_rankings:
                validated_rankings[source] = valid_rankings
                logger.info(f"Validated {len(valid_rankings)} rankings from {source}")
        
        if not validated_rankings:
            logger.error("No valid rankings to aggregate")
            return []
        
        # First, normalize and merge all players
        all_players = self._merge_players(validated_rankings)
        
        # Calculate consensus rankings
        consensus_rankings = self._calculate_consensus(all_players, validated_rankings)
        
        # Sort by consensus rank
        consensus_rankings.sort(key=lambda x: x.consensus_rank)
        
        # Assign position ranks
        self._assign_position_ranks(consensus_rankings)
        
        # Assign tiers
        self._assign_tiers(consensus_rankings)
        
        # Add projections
        consensus_rankings = self.projection_calculator.add_projections(consensus_rankings)
        
        # Calculate VORP if requested
        if use_vbd:
            consensus_rankings = self.vbd_calculator.create_draft_board(
                consensus_rankings, vbd_baseline
            )
            logger.info(f"Applied VBD with {vbd_baseline.value} baseline")
        
        logger.info(f"Generated {len(consensus_rankings)} consensus rankings")
        
        return consensus_rankings
    
    def _merge_players(self, source_rankings: Dict[str, List[Ranking]]) -> List[Player]:
        """Merge all unique players from all sources"""
        player_lists = []
        
        for source, rankings in source_rankings.items():
            players = [r.player for r in rankings]
            player_lists.append(players)
        
        # Use normalizer to merge and deduplicate
        return self.normalizer.merge_player_lists(*player_lists)
    
    def _calculate_consensus(self, all_players: List[Player], 
                           source_rankings: Dict[str, List[Ranking]]) -> List[ConsensusRanking]:
        """Calculate consensus rankings for all players"""
        consensus_list = []
        
        # Create lookup dictionaries for each source
        source_lookups = {}
        for source, rankings in source_rankings.items():
            lookup = {}
            for ranking in rankings:
                # Find the canonical player
                canonical = self.normalizer.find_player_match(
                    ranking.player.name,
                    ranking.player.team,
                    ranking.player.position,
                    all_players
                )
                if canonical:
                    lookup[canonical] = ranking
            source_lookups[source] = lookup
        
        # Calculate consensus for each player
        for player in all_players:
            ranks_by_source = {}
            weighted_ranks = []
            
            # Collect ranks from each source
            for source, lookup in source_lookups.items():
                if player in lookup:
                    rank = lookup[player].rank
                    ranks_by_source[source] = rank
                    
                    # Add weighted rank
                    weight = self.source_weights.get(source, 1.0)
                    weighted_ranks.append((rank, weight))
            
            # Skip if no sources have this player
            if not ranks_by_source:
                continue
            
            # Calculate weighted average rank
            if weighted_ranks:
                total_weight = sum(w for _, w in weighted_ranks)
                consensus_rank = sum(r * w for r, w in weighted_ranks) / total_weight
            else:
                consensus_rank = 999  # Not ranked
            
            # Calculate statistics
            ranks = list(ranks_by_source.values())
            std_dev = statistics.stdev(ranks) if len(ranks) > 1 else 0
            
            consensus = ConsensusRanking(
                player=player,
                consensus_rank=consensus_rank,
                sources=ranks_by_source,
                tier=1,  # Will be assigned later
                std_deviation=std_dev,
                min_rank=min(ranks) if ranks else None,
                max_rank=max(ranks) if ranks else None
            )
            
            consensus_list.append(consensus)
        
        return consensus_list
    
    def _assign_position_ranks(self, rankings: List[ConsensusRanking]) -> None:
        """Assign position-specific rankings"""
        # Group by position
        by_position = defaultdict(list)
        for ranking in rankings:
            by_position[ranking.player.position].append(ranking)
        
        # Sort each position and assign ranks
        for position, position_rankings in by_position.items():
            position_rankings.sort(key=lambda x: x.consensus_rank)
            
            for i, ranking in enumerate(position_rankings, 1):
                ranking.position_rank = i
    
    def _assign_tiers(self, rankings: List[ConsensusRanking]) -> None:
        """Assign tiers to rankings based on position and rank"""
        # Group by position
        by_position = defaultdict(list)
        for ranking in rankings:
            by_position[ranking.player.position].append(ranking)
        
        # Assign tiers for each position
        for position, position_rankings in by_position.items():
            # Sort by consensus rank
            position_rankings.sort(key=lambda x: x.consensus_rank)
            
            # Get tier sizes for this position
            tier_sizes = DEFAULT_TIER_SIZES.get(position.value, [12, 12, 12, 12])
            
            # Assign tiers
            current_tier = 1
            players_in_tier = 0
            tier_index = 0
            
            for ranking in position_rankings:
                ranking.tier = current_tier
                players_in_tier += 1
                
                # Check if we should move to next tier
                if tier_index < len(tier_sizes) and players_in_tier >= tier_sizes[tier_index]:
                    current_tier += 1
                    players_in_tier = 0
                    tier_index += 1
    
    def get_top_players(self, rankings: List[ConsensusRanking], 
                       count: int = 200,
                       position: Optional[Position] = None) -> List[ConsensusRanking]:
        """Get top N players, optionally filtered by position"""
        filtered = rankings
        
        if position:
            filtered = [r for r in rankings if r.player.position == position]
        
        return filtered[:count]
    
    def get_tier_analysis(self, rankings: List[ConsensusRanking]) -> Dict[Position, Dict[int, List[ConsensusRanking]]]:
        """Get rankings organized by position and tier"""
        analysis = defaultdict(lambda: defaultdict(list))
        
        for ranking in rankings:
            position = ranking.player.position
            tier = ranking.tier
            analysis[position][tier].append(ranking)
        
        return dict(analysis)
    
    def get_position_scarcity(self, rankings: List[ConsensusRanking], 
                            roster_requirements: Dict[Position, int],
                            num_teams: int = 12) -> Dict[Position, float]:
        """Calculate position scarcity based on roster requirements"""
        scarcity = {}
        
        for position, required in roster_requirements.items():
            if position == Position.FLEX:
                continue  # Skip flex for scarcity calculation
            
            # Total needed across all teams
            total_needed = required * num_teams
            
            # Count quality starters (top 3 tiers)
            position_rankings = [r for r in rankings if r.player.position == position]
            quality_starters = len([r for r in position_rankings if r.tier <= 3])
            
            # Calculate scarcity (higher = more scarce)
            if quality_starters > 0:
                scarcity[position] = total_needed / quality_starters
            else:
                scarcity[position] = float('inf')
        
        return scarcity