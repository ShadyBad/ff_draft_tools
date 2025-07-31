"""Player name normalization and matching"""
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from fuzzywuzzy import fuzz
from fuzzywuzzy import process

from src.core.models import Player, Position, NFLTeam
from config import DATA_DIR


logger = logging.getLogger(__name__)


class PlayerNormalizer:
    """Handles player name variations and matching across sources"""
    
    def __init__(self):
        self.known_aliases = self._load_known_aliases()
        self.name_cache = {}
        
        # Common name patterns to normalize
        self.suffix_pattern = re.compile(r'\s+(Jr\.?|Sr\.?|III?|IV|V)$', re.IGNORECASE)
        self.punctuation_pattern = re.compile(r'[^\w\s-]')
    
    def _load_known_aliases(self) -> Dict[str, List[str]]:
        """Load known player name aliases from file"""
        aliases_file = DATA_DIR / 'player_mappings.json'
        
        # Default aliases for common variations
        default_aliases = {
            # Name variations
            "CeeDee Lamb": ["C.D. Lamb", "Cedarian Lamb", "CD Lamb"],
            "D.K. Metcalf": ["DK Metcalf", "D.K Metcalf", "DeKaylin Metcalf"],
            "A.J. Brown": ["AJ Brown", "Arthur Brown"],
            "T.J. Hockenson": ["TJ Hockenson", "T.J Hockenson"],
            "D.J. Moore": ["DJ Moore", "Denniston Moore"],
            "K.J. Osborn": ["KJ Osborn", "Kendrick Osborn"],
            
            # Suffix variations
            "Patrick Mahomes": ["Patrick Mahomes II"],
            "Odell Beckham Jr.": ["Odell Beckham", "OBJ"],
            "Marvin Jones Jr.": ["Marvin Jones"],
            "Michael Pittman Jr.": ["Michael Pittman"],
            "Gardner Minshew": ["Gardner Minshew II"],
            
            # Team defenses
            "49ers D/ST": ["San Francisco D/ST", "SF D/ST", "49ers DST", "San Francisco Defense"],
            "Bears D/ST": ["Chicago D/ST", "CHI D/ST", "Bears DST", "Chicago Defense"],
            "Bills D/ST": ["Buffalo D/ST", "BUF D/ST", "Bills DST", "Buffalo Defense"],
            
            # Common nicknames
            "Kenneth Walker III": ["Kenneth Walker", "K. Walker III"],
            "Brian Robinson Jr.": ["Brian Robinson", "B. Robinson Jr."],
        }
        
        if aliases_file.exists():
            try:
                with open(aliases_file, 'r') as f:
                    loaded_aliases = json.load(f)
                    # Merge with defaults
                    for key, values in loaded_aliases.items():
                        if key in default_aliases:
                            default_aliases[key].extend(values)
                        else:
                            default_aliases[key] = values
            except Exception as e:
                logger.warning(f"Could not load player aliases file: {e}")
        
        return default_aliases
    
    def normalize_name(self, name: str) -> str:
        """Normalize a player name for consistent comparison"""
        # Remove extra whitespace
        name = ' '.join(name.split())
        
        # Handle common replacements
        name = name.replace("'", "")  # D'Andre -> DAndre
        
        # Normalize dots in initials
        name = re.sub(r'([A-Z])\.([A-Z])', r'\1.\2', name)  # D.K -> D.K
        name = re.sub(r'([A-Z])\.?\s+([A-Z])\s+', r'\1.\2. ', name)  # D K -> D.K.
        
        # Remove Jr/Sr/III suffixes for comparison
        normalized = self.suffix_pattern.sub('', name).strip()
        
        return normalized
    
    def find_player_match(self, name: str, team: Optional[NFLTeam] = None, 
                         position: Optional[Position] = None,
                         candidates: List[Player] = None) -> Optional[Player]:
        """Find the best matching player from candidates"""
        
        # Check cache first
        cache_key = (name, team, position)
        if cache_key in self.name_cache and candidates is None:
            return self.name_cache[cache_key]
        
        # Direct match in known aliases
        for canonical_name, aliases in self.known_aliases.items():
            if name == canonical_name or name in aliases:
                # If we have candidates, find the matching one
                if candidates:
                    for candidate in candidates:
                        if (candidate.name == canonical_name or 
                            self.normalize_name(candidate.name) == self.normalize_name(canonical_name)):
                            if self._validate_match(candidate, team, position):
                                self.name_cache[cache_key] = candidate
                                return candidate
        
        # If no candidates provided, can't do fuzzy matching
        if not candidates:
            return None
        
        # Normalize the search name
        normalized_search = self.normalize_name(name)
        
        # Try exact match first
        for candidate in candidates:
            if self.normalize_name(candidate.name) == normalized_search:
                if self._validate_match(candidate, team, position):
                    self.name_cache[cache_key] = candidate
                    return candidate
        
        # Fuzzy matching
        best_match = self._fuzzy_match(name, candidates, team, position)
        if best_match:
            self.name_cache[cache_key] = best_match
            return best_match
        
        return None
    
    def _validate_match(self, candidate: Player, team: Optional[NFLTeam], 
                       position: Optional[Position]) -> bool:
        """Validate if a candidate matches the criteria"""
        if team and candidate.team != team:
            return False
        if position and candidate.position != position:
            return False
        return True
    
    def _fuzzy_match(self, name: str, candidates: List[Player],
                    team: Optional[NFLTeam], position: Optional[Position],
                    threshold: int = 85) -> Optional[Player]:
        """Use fuzzy matching to find the best player match"""
        # Filter candidates by team and position if provided
        filtered = [c for c in candidates if self._validate_match(c, team, position)]
        
        if not filtered:
            filtered = candidates
        
        # Prepare names for matching
        candidate_names = [(c, self.normalize_name(c.name)) for c in filtered]
        normalized_search = self.normalize_name(name)
        
        # Find best match
        best_score = 0
        best_candidate = None
        
        for candidate, norm_name in candidate_names:
            # Try different scoring methods
            scores = [
                fuzz.ratio(normalized_search, norm_name),
                fuzz.token_sort_ratio(normalized_search, norm_name),
                fuzz.token_set_ratio(normalized_search, norm_name)
            ]
            
            max_score = max(scores)
            
            # Bonus points for same team/position
            if team and candidate.team == team:
                max_score += 5
            if position and candidate.position == position:
                max_score += 5
            
            if max_score > best_score and max_score >= threshold:
                best_score = max_score
                best_candidate = candidate
        
        if best_candidate and best_score >= threshold:
            logger.debug(f"Fuzzy matched '{name}' to '{best_candidate.name}' (score: {best_score})")
            return best_candidate
        
        return None
    
    def merge_player_lists(self, *player_lists: List[Player]) -> List[Player]:
        """Merge multiple player lists, removing duplicates"""
        seen = {}
        merged = []
        
        for players in player_lists:
            for player in players:
                # Create a key for the player
                key = (self.normalize_name(player.name), player.position, player.team)
                
                if key not in seen:
                    seen[key] = player
                    merged.append(player)
                else:
                    # Update aliases if we've seen this player before
                    existing = seen[key]
                    if player.name != existing.name and player.name not in existing.aliases:
                        existing.aliases.append(player.name)
        
        return merged
    
    def save_new_aliases(self, canonical_name: str, aliases: List[str]) -> None:
        """Save new aliases discovered during processing"""
        if canonical_name not in self.known_aliases:
            self.known_aliases[canonical_name] = []
        
        for alias in aliases:
            if alias not in self.known_aliases[canonical_name]:
                self.known_aliases[canonical_name].append(alias)
        
        # Save to file
        aliases_file = DATA_DIR / 'player_mappings.json'
        try:
            with open(aliases_file, 'w') as f:
                json.dump(self.known_aliases, f, indent=2, sort_keys=True)
        except Exception as e:
            logger.error(f"Could not save player aliases: {e}")