"""
Comprehensive input validation for Fantasy Football Draft Tools
"""
from typing import Dict, List, Optional, Union, Any
from pathlib import Path
import re
# Import moved to avoid circular dependency


class ValidationError(Exception):
    """Custom exception for validation errors"""
    pass


class InputValidator:
    """Validates user inputs and configuration"""
    
    # Valid position codes
    VALID_POSITIONS = {'QB', 'RB', 'WR', 'TE', 'K', 'DST', 'FLEX'}
    
    # Roster size constraints
    MIN_ROSTER_SIZE = 1
    MAX_ROSTER_SIZE = 50
    
    # Team constraints
    MIN_TEAMS = 4
    MAX_TEAMS = 32
    
    # ADP constraints
    MIN_ADP = 1
    MAX_ADP = 500
    
    @staticmethod
    def validate_roster_settings(roster_settings: Dict[str, int]) -> Dict[str, int]:
        """Validate roster configuration settings"""
        if not isinstance(roster_settings, dict):
            raise ValidationError("Roster settings must be a dictionary")
        
        validated = {}
        total_slots = 0
        
        for position, count in roster_settings.items():
            # Validate position
            pos = position.upper()
            if pos not in InputValidator.VALID_POSITIONS:
                raise ValidationError(f"Invalid position: {position}. Valid positions: {', '.join(InputValidator.VALID_POSITIONS)}")
            
            # Validate count
            if not isinstance(count, int):
                raise ValidationError(f"Roster count for {position} must be an integer")
            
            if count < 0:
                raise ValidationError(f"Roster count for {position} cannot be negative")
            
            if count > 10:  # Reasonable limit per position
                raise ValidationError(f"Roster count for {position} seems too high: {count}")
            
            validated[pos] = count
            total_slots += count
        
        # Validate total roster size
        if total_slots < InputValidator.MIN_ROSTER_SIZE:
            raise ValidationError(f"Total roster size must be at least {InputValidator.MIN_ROSTER_SIZE}")
        
        if total_slots > InputValidator.MAX_ROSTER_SIZE:
            raise ValidationError(f"Total roster size cannot exceed {InputValidator.MAX_ROSTER_SIZE}")
        
        return validated
    
    @staticmethod
    def validate_scoring_system(scoring_system: str) -> str:
        """Validate and convert scoring system string"""
        if not scoring_system:
            raise ValidationError("Scoring system cannot be empty")
        
        # Valid scoring systems from config
        valid_systems = ["STANDARD", "HALF_PPR", "PPR"]
        scoring_upper = scoring_system.upper()
        
        if scoring_upper not in valid_systems:
            raise ValidationError(f"Invalid scoring system: {scoring_system}. Valid options: {', '.join(valid_systems)}")
        
        return scoring_upper
    
    @staticmethod
    def validate_vbd_baseline(baseline: str):
        """Validate VBD baseline selection"""
        # Import here to avoid circular dependency
        from src.core.vbd import VBDBaseline
        
        if not baseline:
            raise ValidationError("VBD baseline cannot be empty")
        
        try:
            # VBDBaseline enum values are lowercase
            return VBDBaseline(baseline.lower())
        except ValueError:
            valid_baselines = [b.value for b in VBDBaseline]
            raise ValidationError(f"Invalid VBD baseline: {baseline}. Valid options: {', '.join(valid_baselines)}")
    
    @staticmethod
    def validate_team_count(teams: int) -> int:
        """Validate number of teams in league"""
        if not isinstance(teams, int):
            raise ValidationError("Number of teams must be an integer")
        
        if teams < InputValidator.MIN_TEAMS:
            raise ValidationError(f"Number of teams must be at least {InputValidator.MIN_TEAMS}")
        
        if teams > InputValidator.MAX_TEAMS:
            raise ValidationError(f"Number of teams cannot exceed {InputValidator.MAX_TEAMS}")
        
        return teams
    
    @staticmethod
    def validate_file_path(path: Union[str, Path], must_exist: bool = False) -> Path:
        """Validate file path"""
        try:
            path_obj = Path(path)
        except Exception as e:
            raise ValidationError(f"Invalid file path: {e}")
        
        if must_exist and not path_obj.exists():
            raise ValidationError(f"Path does not exist: {path}")
        
        return path_obj
    
    @staticmethod
    def validate_player_name(name: str) -> str:
        """Validate and clean player name"""
        if not name or not isinstance(name, str):
            raise ValidationError("Player name must be a non-empty string")
        
        # Remove excessive whitespace
        cleaned = ' '.join(name.split())
        
        # Check for reasonable length
        if len(cleaned) < 2:
            raise ValidationError("Player name too short")
        
        if len(cleaned) > 100:
            raise ValidationError("Player name too long")
        
        # Check for valid characters (letters, spaces, hyphens, apostrophes, periods)
        if not re.match(r"^[a-zA-Z\s\-'\.]+$", cleaned):
            raise ValidationError(f"Player name contains invalid characters: {name}")
        
        return cleaned
    
    @staticmethod
    def validate_team_abbreviation(team: str) -> str:
        """Validate NFL team abbreviation"""
        if not team or not isinstance(team, str):
            raise ValidationError("Team abbreviation must be a non-empty string")
        
        # FA is valid for Free Agent
        if team.upper() == 'FA':
            return 'FA'
        
        # Standard team abbreviations are 2-3 characters
        if len(team) < 2 or len(team) > 3:
            raise ValidationError(f"Invalid team abbreviation length: {team}")
        
        # Should be uppercase letters only
        if not re.match(r"^[A-Z]+$", team.upper()):
            raise ValidationError(f"Team abbreviation should contain only letters: {team}")
        
        return team.upper()
    
    @staticmethod
    def validate_adp(adp: Union[int, float]) -> float:
        """Validate Average Draft Position"""
        try:
            adp_float = float(adp)
        except (TypeError, ValueError):
            raise ValidationError(f"ADP must be a number: {adp}")
        
        if adp_float < InputValidator.MIN_ADP:
            raise ValidationError(f"ADP cannot be less than {InputValidator.MIN_ADP}")
        
        if adp_float > InputValidator.MAX_ADP:
            raise ValidationError(f"ADP cannot exceed {InputValidator.MAX_ADP}")
        
        return adp_float
    
    @staticmethod
    def validate_bye_week(bye: Union[int, str, None]) -> Optional[int]:
        """Validate bye week number"""
        if bye is None or bye == '' or bye == 'FA' or bye == 0:
            return None
        
        try:
            bye_int = int(bye)
        except (TypeError, ValueError):
            raise ValidationError(f"Bye week must be a number or empty: {bye}")
        
        # NFL regular season is 18 weeks
        if bye_int < 1 or bye_int > 18:
            raise ValidationError(f"Bye week must be between 1 and 18: {bye_int}")
        
        return bye_int
    
    @staticmethod
    def validate_draft_pick(pick: int, total_teams: int) -> int:
        """Validate draft pick number"""
        if not isinstance(pick, int):
            raise ValidationError("Draft pick must be an integer")
        
        if pick < 1:
            raise ValidationError("Draft pick must be positive")
        
        # Reasonable limit for draft picks
        max_picks = total_teams * 30  # 30 rounds max
        if pick > max_picks:
            raise ValidationError(f"Draft pick {pick} exceeds reasonable limit for {total_teams} teams")
        
        return pick
    
    @staticmethod
    def validate_cli_arguments(args: Any) -> Any:
        """Validate command line arguments"""
        # Validate sources if provided
        if hasattr(args, 'sources') and args.sources:
            valid_sources = {'fantasypros', 'espn', 'yahoo'}  # Add more as implemented
            for source in args.sources:
                if source.lower() not in valid_sources:
                    raise ValidationError(f"Invalid source: {source}. Valid sources: {', '.join(valid_sources)}")
        
        # Validate export format if provided
        if hasattr(args, 'format') and args.format:
            valid_formats = {'csv', 'json', 'sheets'}
            if args.format.lower() not in valid_formats:
                raise ValidationError(f"Invalid format: {args.format}. Valid formats: {', '.join(valid_formats)}")
        
        # Validate VBD settings
        if hasattr(args, 'vbd') and args.vbd:
            if hasattr(args, 'vbd_baseline') and args.vbd_baseline:
                InputValidator.validate_vbd_baseline(args.vbd_baseline)
        
        return args
    
    @staticmethod
    def validate_ranking_data(rankings: List[Dict]) -> List[Dict]:
        """Validate ranking data from scrapers"""
        if not isinstance(rankings, list):
            raise ValidationError("Rankings must be a list")
        
        validated = []
        seen_players = set()
        
        for idx, player in enumerate(rankings):
            if not isinstance(player, dict):
                raise ValidationError(f"Ranking entry {idx} must be a dictionary")
            
            # Required fields
            required_fields = ['name', 'position', 'team']
            for field in required_fields:
                if field not in player:
                    raise ValidationError(f"Ranking entry {idx} missing required field: {field}")
            
            # Validate individual fields
            name = InputValidator.validate_player_name(player['name'])
            
            # Check for duplicates
            player_key = f"{name}_{player['position']}_{player['team']}"
            if player_key in seen_players:
                raise ValidationError(f"Duplicate player found: {name}")
            seen_players.add(player_key)
            
            # Validate position
            if player['position'] not in InputValidator.VALID_POSITIONS:
                raise ValidationError(f"Invalid position for {name}: {player['position']}")
            
            # Validate optional numeric fields
            if 'rank' in player and player['rank'] is not None:
                if not isinstance(player['rank'], (int, float)) or player['rank'] < 1:
                    raise ValidationError(f"Invalid rank for {name}: {player['rank']}")
            
            if 'adp' in player and player['adp'] is not None:
                player['adp'] = InputValidator.validate_adp(player['adp'])
            
            if 'bye_week' in player:
                player['bye_week'] = InputValidator.validate_bye_week(player.get('bye_week'))
            
            validated.append(player)
        
        return validated