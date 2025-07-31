"""Tests for player name normalizer"""
import pytest
from src.core.models import Player, Position, NFLTeam
from src.core.normalizer import PlayerNormalizer


class TestPlayerNormalizer:
    """Test player name normalization and matching"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.normalizer = PlayerNormalizer()
        
        # Create test players
        self.test_players = [
            Player("CeeDee Lamb", Position.WR, NFLTeam.DAL, 7),
            Player("Patrick Mahomes II", Position.QB, NFLTeam.KC, 6),
            Player("A.J. Brown", Position.WR, NFLTeam.PHI, 10),
            Player("D.K. Metcalf", Position.WR, NFLTeam.SEA, 5),
            Player("Travis Kelce", Position.TE, NFLTeam.KC, 6),
        ]
    
    def test_normalize_name(self):
        """Test name normalization"""
        # Test suffix removal
        assert self.normalizer.normalize_name("Patrick Mahomes II") == "Patrick Mahomes"
        assert self.normalizer.normalize_name("Odell Beckham Jr.") == "Odell Beckham"
        
        # Test punctuation handling
        assert self.normalizer.normalize_name("A.J. Brown") == "A.J. Brown"
        assert self.normalizer.normalize_name("D.K Metcalf") == "D.K Metcalf"  # Normalizer preserves existing format
        
        # Test whitespace normalization
        assert self.normalizer.normalize_name("  Travis   Kelce  ") == "Travis Kelce"
    
    def test_exact_match(self):
        """Test exact name matching"""
        player = self.normalizer.find_player_match(
            "Travis Kelce", 
            NFLTeam.KC, 
            Position.TE,
            self.test_players
        )
        assert player is not None
        assert player.name == "Travis Kelce"
    
    def test_alias_match(self):
        """Test matching with known aliases"""
        # Test CeeDee Lamb variations
        player = self.normalizer.find_player_match(
            "C.D. Lamb",
            NFLTeam.DAL,
            Position.WR,
            self.test_players
        )
        assert player is not None
        assert player.name == "CeeDee Lamb"
        
        # Test suffix variation
        player = self.normalizer.find_player_match(
            "Patrick Mahomes",
            NFLTeam.KC,
            Position.QB,
            self.test_players
        )
        assert player is not None
        assert player.name == "Patrick Mahomes II"
    
    def test_fuzzy_match(self):
        """Test fuzzy name matching"""
        # Test with slight misspelling
        player = self.normalizer.find_player_match(
            "AJ Brown",  # Missing dots
            NFLTeam.PHI,
            Position.WR,
            self.test_players
        )
        assert player is not None
        assert player.name == "A.J. Brown"
    
    def test_team_position_validation(self):
        """Test that team and position are validated"""
        # Wrong team should not match
        player = self.normalizer.find_player_match(
            "Travis Kelce",
            NFLTeam.BUF,  # Wrong team
            Position.TE,
            self.test_players
        )
        assert player is None
        
        # Wrong position should not match
        player = self.normalizer.find_player_match(
            "Travis Kelce",
            NFLTeam.KC,
            Position.WR,  # Wrong position
            self.test_players
        )
        assert player is None
    
    def test_merge_player_lists(self):
        """Test merging multiple player lists"""
        list1 = [
            Player("Justin Jefferson", Position.WR, NFLTeam.MIN, 13),
            Player("Christian McCaffrey", Position.RB, NFLTeam.SF, 9),
        ]
        
        list2 = [
            Player("Justin Jefferson", Position.WR, NFLTeam.MIN, 13),  # Duplicate
            Player("Josh Allen", Position.QB, NFLTeam.BUF, 13),
        ]
        
        merged = self.normalizer.merge_player_lists(list1, list2)
        
        # Should have 3 unique players
        assert len(merged) == 3
        
        # Check names are present
        names = [p.name for p in merged]
        assert "Justin Jefferson" in names
        assert "Christian McCaffrey" in names
        assert "Josh Allen" in names