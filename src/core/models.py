"""Core data models for FF Draft Tools"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List
from enum import Enum


class Position(Enum):
    """NFL positions for fantasy football"""
    QB = "QB"
    RB = "RB"
    WR = "WR"
    TE = "TE"
    K = "K"
    DST = "DST"
    FLEX = "FLEX"  # RB/WR/TE


class NFLTeam(Enum):
    """NFL team abbreviations"""
    ARI = "ARI"
    ATL = "ATL"
    BAL = "BAL"
    BUF = "BUF"
    CAR = "CAR"
    CHI = "CHI"
    CIN = "CIN"
    CLE = "CLE"
    DAL = "DAL"
    DEN = "DEN"
    DET = "DET"
    GB = "GB"
    HOU = "HOU"
    IND = "IND"
    JAX = "JAX"  # Jacksonville (some use JAC)
    KC = "KC"
    LAC = "LAC"  # LA Chargers
    LAR = "LAR"  # LA Rams
    LV = "LV"   # Las Vegas
    MIA = "MIA"
    MIN = "MIN"
    NE = "NE"
    NO = "NO"
    NYG = "NYG"
    NYJ = "NYJ"
    PHI = "PHI"
    PIT = "PIT"
    SEA = "SEA"
    SF = "SF"
    TB = "TB"
    TEN = "TEN"
    WAS = "WAS"
    FA = "FA"    # Free Agent (for unsigned/retired players)


@dataclass
class Player:
    """Represents an NFL player"""
    name: str
    position: Position
    team: NFLTeam
    bye_week: int
    player_id: Optional[str] = None  # External ID if available
    
    # Additional metadata
    age: Optional[int] = None
    years_experience: Optional[int] = None
    injury_status: Optional[str] = None
    
    # Name variations for matching
    aliases: List[str] = field(default_factory=list)
    
    def __str__(self) -> str:
        return f"{self.name} ({self.position.value} - {self.team.value})"
    
    def __hash__(self) -> int:
        return hash((self.name, self.position, self.team))


@dataclass
class Ranking:
    """Represents a player's ranking from a source"""
    player: Player
    rank: int
    source: str
    tier: Optional[int] = None
    
    # Optional projections
    projected_points: Optional[float] = None
    
    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)
    notes: Optional[str] = None
    
    def __lt__(self, other: 'Ranking') -> bool:
        return self.rank < other.rank


@dataclass
class ConsensusRanking:
    """Aggregated ranking across multiple sources"""
    player: Player
    consensus_rank: float
    sources: Dict[str, int]  # source -> rank
    tier: int
    
    # Statistical measures
    std_deviation: Optional[float] = None
    min_rank: Optional[int] = None
    max_rank: Optional[int] = None
    
    # Position rank
    position_rank: Optional[int] = None
    
    # ADP if available
    adp: Optional[float] = None
    
    # Projections and value metrics
    projected_points: Optional[float] = None
    vorp: Optional[float] = None  # Value Over Replacement Player
    
    # Risk metrics
    uncertainty_score: Optional[float] = None  # Season-long uncertainty (1-99)
    volatility_score: Optional[float] = None   # Week-to-week volatility
    
    @property
    def average_rank(self) -> float:
        """Get average rank across all sources"""
        if self.sources:
            return sum(self.sources.values()) / len(self.sources)
        return self.consensus_rank
    
    @property
    def variance(self) -> float:
        """Calculate the variance in rankings (for display)"""
        return self.std_deviation if self.std_deviation else 0.0
    
    def rank_variance(self) -> int:
        """Calculate the variance in rankings"""
        if self.min_rank and self.max_rank:
            return self.max_rank - self.min_rank
        return 0
    
    def is_consensus(self) -> bool:
        """Check if sources agree (low variance)"""
        return self.rank_variance() <= 10


@dataclass
class DraftPick:
    """Represents a pick in the draft"""
    round: int
    pick: int
    overall: int
    player: Player
    team_name: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    def __str__(self) -> str:
        return f"Round {self.round}, Pick {self.pick}: {self.player}"


@dataclass
class FantasyTeam:
    """Represents a fantasy team"""
    name: str
    draft_position: int
    roster: Dict[Position, List[Player]] = field(default_factory=dict)
    bench: List[Player] = field(default_factory=list)
    draft_picks: List[DraftPick] = field(default_factory=list)
    
    def add_player(self, player: Player, position: Position) -> None:
        """Add a player to the roster"""
        if position not in self.roster:
            self.roster[position] = []
        self.roster[position].append(player)
    
    def get_roster_needs(self, roster_requirements: Dict[Position, int]) -> Dict[Position, int]:
        """Calculate remaining roster needs"""
        needs = {}
        for pos, required in roster_requirements.items():
            current = len(self.roster.get(pos, []))
            if current < required:
                needs[pos] = required - current
        return needs


@dataclass
class LeagueSettings:
    """Fantasy league configuration"""
    name: str
    teams: int
    scoring_system: str  # STANDARD, HALF_PPR, PPR
    roster_positions: Dict[Position, int]
    bench_spots: int
    draft_rounds: int
    
    # Scoring details
    scoring_values: Dict[str, float] = field(default_factory=dict)
    
    # Additional settings
    waiver_type: str = "FAAB"
    trade_deadline_week: int = 10
    playoff_teams: int = 6
    playoff_weeks: List[int] = field(default_factory=lambda: [14, 15, 16])
    
    def total_roster_spots(self) -> int:
        """Calculate total roster spots"""
        return sum(self.roster_positions.values()) + self.bench_spots