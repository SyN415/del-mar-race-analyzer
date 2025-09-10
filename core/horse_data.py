#!/usr/bin/env python3
"""
Horse Racing Data Structures
Core data models for horse racing analysis
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime

@dataclass
class WorkoutData:
    """Structure for workout information"""
    date: str
    track: str
    distance: str
    time: str
    track_condition: str
    workout_type: str  # 'b' for breeze, 'h' for handily, etc.
    
@dataclass
class ResultData:
    """Structure for past performance results"""
    date: str
    track: str
    distance: str
    surface: str
    finish_position: int
    speed_score: int  # E column speed figure
    final_time: str
    beaten_lengths: float
    odds: str
    race_type: str = ""
    purse: str = ""

@dataclass
class Horse:
    """Data structure for individual horse information"""
    name: str
    post_position: int
    jockey: str
    trainer: str
    weight: int
    morning_line_odds: str
    age: int
    sex: str
    medication: str = ""
    claiming_price: Optional[int] = None
    sire: str = ""
    dam: str = ""
    breeder: str = ""
    owner: str = ""
    equipment_changes: str = ""

    # Links to Equibase profile (if available from entries)
    profile_url: str = ""
    refno: Optional[str] = None
    registry: Optional[str] = None

    # Performance metrics (to be populated from Results tab)
    avg_speed_score: Optional[float] = None
    recent_speed_scores: List[int] = field(default_factory=list)

    # Workout data (to be populated from Workouts tab)
    recent_workouts: List[WorkoutData] = field(default_factory=list)
    avg_workout_time_4f: Optional[float] = None
    avg_workout_time_5f: Optional[float] = None
    avg_workout_time_6f: Optional[float] = None

    # Historical performance data
    results: List[ResultData] = field(default_factory=list)

@dataclass
class Race:
    """Data structure for race information"""
    race_number: int
    post_time: str
    race_type: str
    purse: str
    distance: str
    surface: str
    conditions: str
    horses: List[Horse]
    
    # Track conditions
    track_condition: str = "Fast"  # Default, to be updated
    rail_position: str = ""
    race_date: str = ""
    track_code: str = "DMR"  # Del Mar

@dataclass
class RaceCard:
    """Complete race card for a racing day"""
    date: str
    track: str
    track_code: str
    races: List[Race]
    total_races: int = 0  # computed in __post_init__

    def __post_init__(self):
        self.total_races = len(self.races)

@dataclass
class PredictionFactors:
    """Factors used in race prediction"""
    speed_rating: float = 0.0
    class_rating: float = 0.0
    form_rating: float = 0.0
    workout_rating: float = 0.0
    jockey_rating: float = 0.0
    trainer_rating: float = 0.0
    equipment_rating: float = 0.0
    pace_rating: float = 0.0
    distance_rating: float = 0.0
    surface_rating: float = 0.0

@dataclass
class HorsePrediction:
    """Prediction data for a single horse"""
    horse: Horse
    composite_rating: float
    win_probability: float
    factors: PredictionFactors
    reasoning: str = ""

@dataclass
class RacePrediction:
    """Complete prediction for a race"""
    race: Race
    predictions: List[HorsePrediction]
    top_pick: Optional[HorsePrediction] = None
    exotic_suggestions: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.predictions:
            # Sort predictions by composite rating
            self.predictions.sort(key=lambda x: x.composite_rating, reverse=True)
            self.top_pick = self.predictions[0]

@dataclass
class RaceCardPredictions:
    """Complete predictions for an entire race card"""
    race_card: RaceCard
    predictions: List[RacePrediction]
    generated_at: datetime
    best_bets: List[HorsePrediction] = field(default_factory=list)
    
    def __post_init__(self):
        self.generated_at = datetime.now()
        # Identify best bets (highest rated horses across all races)
        all_predictions = []
        for race_pred in self.predictions:
            all_predictions.extend(race_pred.predictions)
        
        # Sort by composite rating and take top 3
        all_predictions.sort(key=lambda x: x.composite_rating, reverse=True)
        self.best_bets = all_predictions[:3]
