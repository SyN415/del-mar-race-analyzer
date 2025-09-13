#!/usr/bin/env python3
"""
Validation Framework for Del Mar Race Analyzer
Implements automated backtesting, accuracy tracking, and performance monitoring
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import statistics

logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    """Results from validation testing"""
    accuracy: float
    total_predictions: int
    correct_predictions: int
    surface_breakdown: Dict[str, float]
    distance_breakdown: Dict[str, float]
    confidence_correlation: float
    timestamp: str

class ValidationFramework:
    """
    Automated validation and backtesting system
    
    Features:
    - Historical race outcome validation
    - Accuracy tracking across different conditions
    - Performance monitoring and reporting
    - Industry benchmark comparison
    """
    
    def __init__(self, historical_data_path: str = "del_mar_09_05_2025_races.json"):
        """
        Initialize validation framework
        
        Args:
            historical_data_path: Path to historical race data with outcomes
        """
        self.historical_data_path = historical_data_path
        self.validation_history = []
        self.industry_benchmark = 18.5  # Industry standard accuracy percentage
        
        # Load historical validation results
        self._load_validation_history()
    
    def run_backtest(self, prediction_engine, start_date: str = None, end_date: str = None) -> ValidationResult:
        """
        Run comprehensive backtest against historical data
        
        Args:
            prediction_engine: RacePredictionEngine instance
            start_date: Start date for backtesting (YYYY-MM-DD)
            end_date: End date for backtesting (YYYY-MM-DD)
            
        Returns:
            ValidationResult: Comprehensive validation metrics
        """
        logger.info("Starting backtest validation")
        
        # Load historical data
        historical_races = self._load_historical_data()
        if not historical_races:
            logger.error("No historical data available for backtesting")
            return self._create_empty_result()
        
        # Filter by date range if specified
        if start_date or end_date:
            historical_races = self._filter_by_date_range(historical_races, start_date, end_date)
        
        total_predictions = 0
        correct_predictions = 0
        surface_results = {}
        distance_results = {}
        confidence_scores = []
        accuracy_scores = []
        
        for race_data in historical_races:
            try:
                # Skip races without outcome data
                if not self._has_race_outcomes(race_data):
                    continue
                
                # Create horse data collection from historical data
                horse_data_collection = self._extract_horse_data(race_data)
                
                # Generate predictions
                predictions = prediction_engine.predict_race(race_data, horse_data_collection)
                
                if not predictions.get('predictions'):
                    continue
                
                # Validate predictions against actual outcomes
                race_accuracy, race_total = self._validate_race_predictions(
                    predictions['predictions'], race_data
                )
                
                total_predictions += race_total
                correct_predictions += race_accuracy
                
                # Track by surface and distance
                surface = race_data.get('surface', 'Unknown')
                distance = race_data.get('distance', 'Unknown')
                
                if surface not in surface_results:
                    surface_results[surface] = {'correct': 0, 'total': 0}
                if distance not in distance_results:
                    distance_results[distance] = {'correct': 0, 'total': 0}
                
                surface_results[surface]['correct'] += race_accuracy
                surface_results[surface]['total'] += race_total
                distance_results[distance]['correct'] += race_accuracy
                distance_results[distance]['total'] += race_total
                
                # Track confidence correlation
                if predictions.get('top_pick'):
                    confidence = predictions['top_pick'].get('composite_rating', 0)
                    actual_winner = self._get_race_winner(race_data)
                    predicted_winner = predictions['top_pick'].get('name', '')
                    
                    confidence_scores.append(confidence)
                    accuracy_scores.append(1.0 if predicted_winner == actual_winner else 0.0)
                
            except Exception as e:
                logger.warning(f"Error processing race for validation: {e}")
                continue
        
        # Calculate overall accuracy
        overall_accuracy = (correct_predictions / total_predictions * 100) if total_predictions > 0 else 0.0
        
        # Calculate surface and distance breakdowns
        surface_breakdown = {}
        for surface, results in surface_results.items():
            if results['total'] > 0:
                surface_breakdown[surface] = (results['correct'] / results['total']) * 100
        
        distance_breakdown = {}
        for distance, results in distance_results.items():
            if results['total'] > 0:
                distance_breakdown[distance] = (results['correct'] / results['total']) * 100
        
        # Calculate confidence correlation
        confidence_correlation = 0.0
        if len(confidence_scores) > 1 and len(accuracy_scores) > 1:
            try:
                confidence_correlation = statistics.correlation(confidence_scores, accuracy_scores)
            except statistics.StatisticsError:
                confidence_correlation = 0.0
        
        # Create validation result
        result = ValidationResult(
            accuracy=overall_accuracy,
            total_predictions=total_predictions,
            correct_predictions=correct_predictions,
            surface_breakdown=surface_breakdown,
            distance_breakdown=distance_breakdown,
            confidence_correlation=confidence_correlation,
            timestamp=datetime.now().isoformat()
        )
        
        # Save result to history
        self._save_validation_result(result)
        
        logger.info(f"Backtest completed: {overall_accuracy:.1f}% accuracy ({correct_predictions}/{total_predictions})")
        
        return result
    
    def get_accuracy_trend(self, days: int = 30) -> List[Dict]:
        """Get accuracy trend over specified number of days"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        recent_results = [
            result for result in self.validation_history
            if datetime.fromisoformat(result['timestamp']) >= cutoff_date
        ]
        
        return sorted(recent_results, key=lambda x: x['timestamp'])
    
    def compare_to_industry_benchmark(self, current_accuracy: float) -> Dict:
        """Compare current accuracy to industry benchmark"""
        return {
            'current_accuracy': current_accuracy,
            'industry_benchmark': self.industry_benchmark,
            'performance_vs_benchmark': current_accuracy - self.industry_benchmark,
            'meets_benchmark': current_accuracy >= self.industry_benchmark,
            'improvement_needed': max(0, self.industry_benchmark - current_accuracy)
        }
    
    def generate_validation_report(self, result: ValidationResult) -> Dict:
        """Generate comprehensive validation report"""
        benchmark_comparison = self.compare_to_industry_benchmark(result.accuracy)
        
        return {
            'validation_summary': {
                'accuracy': f"{result.accuracy:.1f}%",
                'total_predictions': result.total_predictions,
                'correct_predictions': result.correct_predictions,
                'timestamp': result.timestamp
            },
            'performance_analysis': {
                'vs_industry_benchmark': benchmark_comparison,
                'confidence_correlation': f"{result.confidence_correlation:.3f}",
                'grade': self._calculate_grade(result.accuracy)
            },
            'breakdown_analysis': {
                'by_surface': result.surface_breakdown,
                'by_distance': result.distance_breakdown
            },
            'recommendations': self._generate_recommendations(result)
        }
    
    def _load_historical_data(self) -> List[Dict]:
        """Load historical race data"""
        try:
            if os.path.exists(self.historical_data_path):
                with open(self.historical_data_path, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
                    elif isinstance(data, dict) and 'races' in data:
                        return data['races']
            return []
        except Exception as e:
            logger.error(f"Failed to load historical data: {e}")
            return []
    
    def _filter_by_date_range(self, races: List[Dict], start_date: str, end_date: str) -> List[Dict]:
        """Filter races by date range"""
        # Implementation would filter races by date
        # For now, return all races
        return races
    
    def _has_race_outcomes(self, race_data: Dict) -> bool:
        """Check if race has outcome data"""
        horses = race_data.get('horses', [])
        return any(horse.get('finish_position') for horse in horses)
    
    def _extract_horse_data(self, race_data: Dict) -> Dict:
        """Extract horse data collection from race data"""
        horse_data_collection = {}
        for horse in race_data.get('horses', []):
            horse_name = horse.get('name', '')
            if horse_name:
                horse_data_collection[horse_name] = horse
        return horse_data_collection
    
    def _validate_race_predictions(self, predictions: List[Dict], race_data: Dict) -> Tuple[int, int]:
        """Validate predictions against actual race outcomes"""
        if not predictions:
            return 0, 0
        
        # Get actual winner
        actual_winner = self._get_race_winner(race_data)
        if not actual_winner:
            return 0, 0
        
        # Check if top prediction matches actual winner
        top_prediction = predictions[0] if predictions else {}
        predicted_winner = top_prediction.get('name', '')
        
        correct = 1 if predicted_winner == actual_winner else 0
        return correct, 1
    
    def _get_race_winner(self, race_data: Dict) -> str:
        """Get the actual winner of the race"""
        horses = race_data.get('horses', [])
        for horse in horses:
            if horse.get('finish_position') == 1:
                return horse.get('name', '')
        return ''
    
    def _load_validation_history(self):
        """Load historical validation results"""
        try:
            if os.path.exists('validation_history.json'):
                with open('validation_history.json', 'r') as f:
                    self.validation_history = json.load(f)
        except Exception as e:
            logger.warning(f"Could not load validation history: {e}")
            self.validation_history = []
    
    def _save_validation_result(self, result: ValidationResult):
        """Save validation result to history"""
        result_dict = {
            'accuracy': result.accuracy,
            'total_predictions': result.total_predictions,
            'correct_predictions': result.correct_predictions,
            'surface_breakdown': result.surface_breakdown,
            'distance_breakdown': result.distance_breakdown,
            'confidence_correlation': result.confidence_correlation,
            'timestamp': result.timestamp
        }
        
        self.validation_history.append(result_dict)
        
        # Keep only last 100 results
        self.validation_history = self.validation_history[-100:]
        
        try:
            with open('validation_history.json', 'w') as f:
                json.dump(self.validation_history, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save validation history: {e}")
    
    def _create_empty_result(self) -> ValidationResult:
        """Create empty validation result"""
        return ValidationResult(
            accuracy=0.0,
            total_predictions=0,
            correct_predictions=0,
            surface_breakdown={},
            distance_breakdown={},
            confidence_correlation=0.0,
            timestamp=datetime.now().isoformat()
        )
    
    def _calculate_grade(self, accuracy: float) -> str:
        """Calculate letter grade based on accuracy"""
        if accuracy >= 27.5:
            return "A-"
        elif accuracy >= 22.0:
            return "B+"
        elif accuracy >= 19.5:
            return "B-"
        elif accuracy >= 16.0:
            return "C+"
        elif accuracy >= 14.5:
            return "C"
        elif accuracy >= 12.0:
            return "C-"
        else:
            return "D"
    
    def _generate_recommendations(self, result: ValidationResult) -> List[str]:
        """Generate improvement recommendations based on results"""
        recommendations = []
        
        if result.accuracy < self.industry_benchmark:
            recommendations.append(f"Accuracy below industry benchmark ({self.industry_benchmark}%). Consider model improvements.")
        
        if result.confidence_correlation < 0.3:
            recommendations.append("Low confidence correlation. Review confidence scoring algorithm.")
        
        if result.total_predictions < 50:
            recommendations.append("Limited validation data. Increase historical data for more reliable metrics.")
        
        # Surface-specific recommendations
        for surface, accuracy in result.surface_breakdown.items():
            if accuracy < result.accuracy - 5:
                recommendations.append(f"Below-average performance on {surface}. Consider surface-specific adjustments.")
        
        return recommendations
