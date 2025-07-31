"""Tests for input validation"""
import pytest
from pathlib import Path

from src.utils.validation import InputValidator, ValidationError
from src.core.vbd import VBDBaseline


class TestInputValidator:
    """Test input validation functionality"""
    
    def test_validate_roster_settings_valid(self):
        """Test valid roster settings"""
        roster = {
            "QB": 1,
            "RB": 2,
            "WR": 3,
            "TE": 1,
            "FLEX": 1,
            "K": 1,
            "DST": 1
        }
        validated = InputValidator.validate_roster_settings(roster)
        assert validated == {k.upper(): v for k, v in roster.items()}
    
    def test_validate_roster_settings_invalid_position(self):
        """Test roster settings with invalid position"""
        roster = {"QB": 1, "INVALID": 1}
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_roster_settings(roster)
        assert "Invalid position: INVALID" in str(exc_info.value)
    
    def test_validate_roster_settings_negative_count(self):
        """Test roster settings with negative count"""
        roster = {"QB": -1}
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_roster_settings(roster)
        assert "cannot be negative" in str(exc_info.value)
    
    def test_validate_roster_settings_too_large(self):
        """Test roster settings with too many players"""
        roster = {"QB": 10, "RB": 10, "WR": 10, "TE": 10, "FLEX": 10, "K": 5}  # 55 total
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_roster_settings(roster)
        assert "Total roster size cannot exceed" in str(exc_info.value)
    
    def test_validate_scoring_system_valid(self):
        """Test valid scoring systems"""
        assert InputValidator.validate_scoring_system("standard") == "STANDARD"
        assert InputValidator.validate_scoring_system("HALF_PPR") == "HALF_PPR"
        assert InputValidator.validate_scoring_system("ppr") == "PPR"
    
    def test_validate_scoring_system_invalid(self):
        """Test invalid scoring system"""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_scoring_system("invalid")
        assert "Invalid scoring system" in str(exc_info.value)
    
    def test_validate_vbd_baseline_valid(self):
        """Test valid VBD baselines"""
        assert InputValidator.validate_vbd_baseline("vols") == VBDBaseline.VOLS
        assert InputValidator.validate_vbd_baseline("VORP") == VBDBaseline.VORP
        assert InputValidator.validate_vbd_baseline("beer") == VBDBaseline.BEER
    
    def test_validate_vbd_baseline_invalid(self):
        """Test invalid VBD baseline"""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_vbd_baseline("invalid")
        assert "Invalid VBD baseline" in str(exc_info.value)
    
    def test_validate_team_count_valid(self):
        """Test valid team counts"""
        assert InputValidator.validate_team_count(10) == 10
        assert InputValidator.validate_team_count(12) == 12
        assert InputValidator.validate_team_count(14) == 14
    
    def test_validate_team_count_too_small(self):
        """Test team count too small"""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_team_count(2)
        assert "at least 4" in str(exc_info.value)
    
    def test_validate_team_count_too_large(self):
        """Test team count too large"""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_team_count(50)
        assert "cannot exceed 32" in str(exc_info.value)
    
    def test_validate_player_name_valid(self):
        """Test valid player names"""
        assert InputValidator.validate_player_name("Patrick Mahomes") == "Patrick Mahomes"
        assert InputValidator.validate_player_name("D'Andre Swift") == "D'Andre Swift"
        assert InputValidator.validate_player_name("T.J. Hockenson") == "T.J. Hockenson"
        assert InputValidator.validate_player_name("  John   Doe  ") == "John Doe"  # Whitespace cleaned
    
    def test_validate_player_name_invalid(self):
        """Test invalid player names"""
        with pytest.raises(ValidationError):
            InputValidator.validate_player_name("")
        
        with pytest.raises(ValidationError):
            InputValidator.validate_player_name("A")  # Too short
        
        with pytest.raises(ValidationError):
            InputValidator.validate_player_name("Player123")  # Numbers not allowed
        
        with pytest.raises(ValidationError):
            InputValidator.validate_player_name("Player@Name")  # Special chars not allowed
    
    def test_validate_team_abbreviation_valid(self):
        """Test valid team abbreviations"""
        assert InputValidator.validate_team_abbreviation("KC") == "KC"
        assert InputValidator.validate_team_abbreviation("sf") == "SF"
        assert InputValidator.validate_team_abbreviation("LAR") == "LAR"
        assert InputValidator.validate_team_abbreviation("FA") == "FA"  # Free agent
    
    def test_validate_team_abbreviation_invalid(self):
        """Test invalid team abbreviations"""
        with pytest.raises(ValidationError):
            InputValidator.validate_team_abbreviation("")
        
        with pytest.raises(ValidationError):
            InputValidator.validate_team_abbreviation("TOOLONG")
        
        with pytest.raises(ValidationError):
            InputValidator.validate_team_abbreviation("K1")  # Numbers not allowed
    
    def test_validate_adp_valid(self):
        """Test valid ADP values"""
        assert InputValidator.validate_adp(1) == 1.0
        assert InputValidator.validate_adp(25.5) == 25.5
        assert InputValidator.validate_adp(300) == 300.0
    
    def test_validate_adp_invalid(self):
        """Test invalid ADP values"""
        with pytest.raises(ValidationError):
            InputValidator.validate_adp(0)
        
        with pytest.raises(ValidationError):
            InputValidator.validate_adp(600)
        
        with pytest.raises(ValidationError):
            InputValidator.validate_adp("not a number")
    
    def test_validate_bye_week_valid(self):
        """Test valid bye weeks"""
        assert InputValidator.validate_bye_week(5) == 5
        assert InputValidator.validate_bye_week(14) == 14
        assert InputValidator.validate_bye_week(None) is None
        assert InputValidator.validate_bye_week("") is None
        assert InputValidator.validate_bye_week(0) is None
        assert InputValidator.validate_bye_week("FA") is None
    
    def test_validate_bye_week_invalid(self):
        """Test invalid bye weeks"""
        with pytest.raises(ValidationError):
            InputValidator.validate_bye_week(20)  # Too high
        
        with pytest.raises(ValidationError):
            InputValidator.validate_bye_week(-1)  # Negative
    
    def test_validate_draft_pick_valid(self):
        """Test valid draft picks"""
        assert InputValidator.validate_draft_pick(1, 12) == 1
        assert InputValidator.validate_draft_pick(100, 12) == 100
        assert InputValidator.validate_draft_pick(360, 12) == 360  # 30 rounds * 12 teams
    
    def test_validate_draft_pick_invalid(self):
        """Test invalid draft picks"""
        with pytest.raises(ValidationError):
            InputValidator.validate_draft_pick(0, 12)
        
        with pytest.raises(ValidationError):
            InputValidator.validate_draft_pick(500, 12)  # Too high for 12 teams
    
    def test_validate_ranking_data_valid(self):
        """Test valid ranking data"""
        rankings = [
            {
                "name": "Patrick Mahomes",
                "position": "QB",
                "team": "KC",
                "rank": 25,
                "adp": 30.5,
                "bye_week": 10
            },
            {
                "name": "Christian McCaffrey",
                "position": "RB",
                "team": "SF",
                "rank": 1,
                "adp": 1.2,
                "bye_week": 11
            }
        ]
        
        validated = InputValidator.validate_ranking_data(rankings)
        assert len(validated) == 2
        assert validated[0]["name"] == "Patrick Mahomes"
        assert validated[1]["adp"] == 1.2
    
    def test_validate_ranking_data_missing_fields(self):
        """Test ranking data with missing required fields"""
        rankings = [{"name": "Player"}]  # Missing position and team
        
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_ranking_data(rankings)
        assert "missing required field" in str(exc_info.value)
    
    def test_validate_ranking_data_duplicates(self):
        """Test ranking data with duplicate players"""
        rankings = [
            {"name": "Player One", "position": "RB", "team": "KC"},
            {"name": "Player One", "position": "RB", "team": "KC"}  # Duplicate
        ]
        
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_ranking_data(rankings)
        assert "Duplicate player found" in str(exc_info.value)
    
    def test_validate_file_path_valid(self):
        """Test valid file paths"""
        # Current file should exist
        current_file = Path(__file__)
        validated = InputValidator.validate_file_path(current_file, must_exist=True)
        assert validated == current_file
        
        # Non-existent path without must_exist
        fake_path = "/tmp/fake_file.txt"
        validated = InputValidator.validate_file_path(fake_path, must_exist=False)
        assert str(validated) == fake_path
    
    def test_validate_file_path_not_exists(self):
        """Test file path that doesn't exist with must_exist=True"""
        fake_path = "/tmp/definitely_does_not_exist_12345.txt"
        
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_file_path(fake_path, must_exist=True)
        assert "does not exist" in str(exc_info.value)