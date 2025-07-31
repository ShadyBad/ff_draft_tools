"""Tests for Value-Based Drafting (VBD) calculations"""
import pytest
from datetime import datetime

from src.core.models import Player, Position, NFLTeam, ConsensusRanking
from src.core.vbd import VBDCalculator, VBDBaseline, VORPResult


class TestVBDCalculator:
    """Test VBD calculator functionality"""
    
    @pytest.fixture
    def league_settings(self):
        """Standard league settings for testing"""
        return {
            "teams": 12,
            "roster": {
                "QB": 1,
                "RB": 2,
                "WR": 2,
                "TE": 1,
                "FLEX": 1,
                "K": 1,
                "DST": 1,
                "BENCH": 6
            }
        }
    
    @pytest.fixture
    def sample_rankings(self):
        """Create sample rankings for testing"""
        rankings = []
        
        # Add QBs
        for i in range(20):
            player = Player(
                name=f"QB{i+1}",
                position=Position.QB,
                team=NFLTeam.KC,
                bye_week=10
            )
            ranking = ConsensusRanking(
                player=player,
                consensus_rank=i+1,
                sources=["test"],
                tier=1 if i < 5 else 2,
                projected_points=400 - (i * 10)  # Decreasing points
            )
            rankings.append(ranking)
        
        # Add RBs
        for i in range(50):
            player = Player(
                name=f"RB{i+1}",
                position=Position.RB,
                team=NFLTeam.SF,
                bye_week=11
            )
            ranking = ConsensusRanking(
                player=player,
                consensus_rank=20 + i + 1,
                sources=["test"],
                tier=1 if i < 10 else 2 if i < 25 else 3,
                projected_points=300 - (i * 5)  # Decreasing points
            )
            rankings.append(ranking)
        
        # Add WRs
        for i in range(60):
            player = Player(
                name=f"WR{i+1}",
                position=Position.WR,
                team=NFLTeam.DAL,
                bye_week=9
            )
            ranking = ConsensusRanking(
                player=player,
                consensus_rank=70 + i + 1,
                sources=["test"],
                tier=1 if i < 10 else 2 if i < 30 else 3,
                projected_points=280 - (i * 4)  # Decreasing points
            )
            rankings.append(ranking)
        
        # Add TEs
        for i in range(20):
            player = Player(
                name=f"TE{i+1}",
                position=Position.TE,
                team=NFLTeam.PHI,
                bye_week=9
            )
            ranking = ConsensusRanking(
                player=player,
                consensus_rank=130 + i + 1,
                sources=["test"],
                tier=1 if i < 3 else 2 if i < 10 else 3,
                projected_points=200 - (i * 8)  # Decreasing points
            )
            rankings.append(ranking)
        
        return rankings
    
    def test_vbd_calculator_init(self, league_settings):
        """Test VBD calculator initialization"""
        calculator = VBDCalculator(league_settings)
        assert calculator.teams == 12
        assert calculator.roster_slots == league_settings["roster"]
        assert calculator.flex_positions == {Position.RB, Position.WR, Position.TE}
    
    def test_calculate_baselines_vols(self, league_settings, sample_rankings):
        """Test VOLS baseline calculation"""
        calculator = VBDCalculator(league_settings)
        baselines = calculator._calculate_baselines(sample_rankings, VBDBaseline.VOLS)
        
        # VOLS baseline should be at the last starter
        # 12 teams * 1 QB = 12th QB
        assert baselines[Position.QB] == pytest.approx(310.0, rel=1e-2)  # QB12 has 310 points
        
        # 12 teams * 2 RB + 7 flex spots (estimated) = ~31st RB
        assert baselines[Position.RB] > 0
        
        # 12 teams * 2 WR + remaining flex = ~31st WR
        assert baselines[Position.WR] > 0
        
        # 12 teams * 1 TE = 12th TE
        assert baselines[Position.TE] == pytest.approx(104.0, rel=1e-2)  # TE12 has 104 points
    
    def test_calculate_baselines_vorp(self, league_settings, sample_rankings):
        """Test VORP baseline calculation"""
        calculator = VBDCalculator(league_settings)
        baselines = calculator._calculate_baselines(sample_rankings, VBDBaseline.VORP)
        
        # VORP uses multipliers - QB baseline should be around 18th QB (12 * 1.5)
        qb_baseline_idx = int(12 * 1.5) - 1
        expected_qb_baseline = 400 - (qb_baseline_idx * 10)
        assert baselines[Position.QB] == pytest.approx(expected_qb_baseline, rel=1e-2)
        
        # RB baseline should be around 42nd RB (12 * 3.5)
        rb_baseline_idx = min(int(12 * 3.5) - 1, 49)  # Cap at available RBs
        expected_rb_baseline = 300 - (rb_baseline_idx * 5)
        assert baselines[Position.RB] == pytest.approx(expected_rb_baseline, rel=1e-2)
    
    def test_calculate_baselines_beer(self, league_settings, sample_rankings):
        """Test BEER baseline calculation"""
        calculator = VBDCalculator(league_settings)
        baselines = calculator._calculate_baselines(sample_rankings, VBDBaseline.BEER)
        
        # BEER accounts for injuries and bye weeks
        # Should be deeper than VORP
        baselines_vorp = calculator._calculate_baselines(sample_rankings, VBDBaseline.VORP)
        
        # BEER baselines should be lower (deeper in rankings) than VORP
        assert baselines[Position.QB] <= baselines_vorp[Position.QB]
        assert baselines[Position.RB] <= baselines_vorp[Position.RB]
        assert baselines[Position.WR] <= baselines_vorp[Position.WR]
        assert baselines[Position.TE] <= baselines_vorp[Position.TE]
    
    def test_calculate_vorp(self, league_settings, sample_rankings):
        """Test VORP calculation"""
        calculator = VBDCalculator(league_settings)
        vorp_results = calculator.calculate_vorp(sample_rankings, VBDBaseline.VORP)
        
        # Check that we got results
        assert len(vorp_results) == len(sample_rankings)
        
        # Check that VORP is calculated correctly
        for result in vorp_results[:5]:  # Check top 5
            assert result.vorp_score > 0  # Top players should have positive VORP
            assert result.vorp_score == result.projected_points - result.baseline_points
        
        # Check that results are sorted by VORP
        vorp_scores = [r.vorp_score for r in vorp_results]
        assert vorp_scores == sorted(vorp_scores, reverse=True)
    
    def test_cross_positional_value(self, league_settings, sample_rankings):
        """Test that VBD correctly identifies cross-positional value"""
        calculator = VBDCalculator(league_settings)
        
        # Add a high-value TE
        elite_te = Player(
            name="Elite TE",
            position=Position.TE,
            team=NFLTeam.KC,
            bye_week=10
        )
        elite_te_ranking = ConsensusRanking(
            player=elite_te,
            consensus_rank=25,  # High ADP
            sources=["test"],
            tier=1,
            projected_points=280  # Very high for a TE
        )
        
        test_rankings = sample_rankings + [elite_te_ranking]
        vorp_results = calculator.calculate_vorp(test_rankings, VBDBaseline.VORP)
        
        # Find the elite TE in results
        elite_te_result = next(r for r in vorp_results if r.player_name == "Elite TE")
        
        # Elite TE should have high VORP due to positional scarcity
        assert elite_te_result.vorp_score > 100  # Should be very valuable
        
        # Find where Elite TE ranks overall by VORP
        vorp_rank = vorp_results.index(elite_te_result) + 1
        assert vorp_rank < 20  # Should be a top-20 pick by VORP despite TE position
    
    def test_empty_rankings(self, league_settings):
        """Test handling of empty rankings"""
        calculator = VBDCalculator(league_settings)
        vorp_results = calculator.calculate_vorp([], VBDBaseline.VORP)
        assert vorp_results == []
    
    def test_missing_projections(self, league_settings):
        """Test handling of players without projections"""
        calculator = VBDCalculator(league_settings)
        
        # Create rankings with some missing projections
        rankings = []
        for i in range(5):
            player = Player(
                name=f"Player{i+1}",
                position=Position.RB,
                team=NFLTeam.KC,
                bye_week=10
            )
            ranking = ConsensusRanking(
                player=player,
                consensus_rank=i+1,
                sources=["test"],
                tier=1,
                projected_points=100.0 if i % 2 == 0 else None  # Every other has no projection
            )
            rankings.append(ranking)
        
        vorp_results = calculator.calculate_vorp(rankings, VBDBaseline.VORP)
        
        # Should only return results for players with projections
        assert len(vorp_results) == 3  # Only 3 players have projections
        assert all(r.projected_points > 0 for r in vorp_results)
    
    def test_baseline_types(self):
        """Test that all baseline types are valid"""
        assert VBDBaseline.VOLS.value == "vols"
        assert VBDBaseline.VORP.value == "vorp"
        assert VBDBaseline.BEER.value == "beer"