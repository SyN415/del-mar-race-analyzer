#!/usr/bin/env python3
"""
Gradient Boosting Model for Horse Race Predictions
Implements XGBoost model with specialized racing features and integration with prediction engine
"""

import json
import pandas as pd
import numpy as np
from xgboost import XGBRegressor
from sklearn.model_selection import cross_val_score, KFold
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

class GradientBoostingPredictor:
    """
    XGBoost-based predictor for horse race outcomes
    
    Features:
    - Speed figures from last 5 races
    - Workout quality metrics
    - Jockey and trainer 90-day win rates
    - Race-specific contextual features
    
    Integration:
    - Designed to work with existing prediction engine through weighted scoring
    - Provides prediction confidence metrics
    """
    
    def __init__(self, historical_data_path: str = "del_mar_09_05_2025_races.json"):
        """
        Initialize and train the gradient boosting model
        
        Args:
            historical_data_path: Path to historical race data JSON file
        """
        self.model = None
        self.feature_names = [
            'avg_speed_last5', 'speed_trend', 'workout_quality',
            'jockey_win_rate_90d', 'trainer_win_rate_90d',
            'distance_match', 'surface_match', 'class_level'
        ]
        self.historical_data_path = historical_data_path
        self.jockey_stats = {}
        self.trainer_stats = {}
        
        try:
            self.train_model()
            logger.info("Gradient Boosting model trained successfully")
        except Exception as e:
            logger.error(f"Failed to train gradient boosting model: {str(e)}")
            raise

    def _load_historical_data(self) -> List[Dict]:
        """Load and parse historical race data"""
        try:
            with open(self.historical_data_path, 'r') as f:
                data = json.load(f)

            # Handle different JSON structures
            if isinstance(data, dict):
                # If it's a dictionary, try to extract races list
                if 'races' in data:
                    return data['races']
                else:
                    logger.warning(f"JSON structure doesn't contain 'races' key, returning empty list")
                    return []
            elif isinstance(data, list):
                # If it's already a list, return it
                return data
            else:
                logger.warning(f"Unexpected JSON structure type: {type(data)}, returning empty list")
                return []

        except FileNotFoundError:
            logger.warning(f"Historical data file not found: {self.historical_data_path}, will use empty training data")
            return []
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in historical data file: {self.historical_data_path}, error: {e}")
            return []
        except Exception as e:
            logger.warning(f"Error loading historical data: {e}")
            return []

    def _calculate_jockey_trainer_stats(self, races: List[Dict]):
        """Calculate 90-day win rates for jockeys and trainers"""
        current_date = datetime.now()
        ninety_days_ago = current_date - timedelta(days=90)
        
        # Reset stats
        self.jockey_stats = {}
        self.trainer_stats = {}
        
        # Process races in chronological order
        for race in sorted(races, key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d')):
            race_date = datetime.strptime(race['date'], '%Y-%m-%d')
            
            # Skip races older than 90 days from current processing point
            if race_date < ninety_days_ago:
                continue
                
            for horse in race.get('horses', []):
                finish = horse.get('finish_position', 0)
                jockey = horse.get('jockey', '')
                trainer = horse.get('trainer', '')
                
                # Update jockey stats
                if jockey:
                    if jockey not in self.jockey_stats:
                        self.jockey_stats[jockey] = {'wins': 0, 'starts': 0}
                    self.jockey_stats[jockey]['starts'] += 1
                    if finish == 1:
                        self.jockey_stats[jockey]['wins'] += 1
                
                # Update trainer stats
                if trainer:
                    if trainer not in self.trainer_stats:
                        self.trainer_stats[trainer] = {'wins': 0, 'starts': 0}
                    self.trainer_stats[trainer]['starts'] += 1
                    if finish == 1:
                        self.trainer_stats[trainer]['wins'] += 1

    def _extract_features(self, horse_data: Dict, race_info: Dict) -> Dict:
        """Extract feature vector for a single horse"""
        features = {
            'avg_speed_last5': 50.0,
            'speed_trend': 0.0,
            'workout_quality': 50.0,
            'jockey_win_rate_90d': 0.0,
            'trainer_win_rate_90d': 0.0,
            'distance_match': 0.5,
            'surface_match': 0.5,
            'class_level': 0.5
        }
        
        # Speed figures from last 5 races
        results = horse_data.get('results', [])
        speed_figures = [r.get('speed_score', 0) for r in results[:5] if 'speed_score' in r]
        
        if speed_figures:
            features['avg_speed_last5'] = np.mean(speed_figures)
            if len(speed_figures) > 1:
                trends = np.diff(speed_figures)
                features['speed_trend'] = np.mean(trends)
        
        # Workout quality (simplified)
        workouts = horse_data.get('workouts', [])
        if workouts:
            # Use the most recent workout time as proxy for quality
            try:
                time_str = workouts[0].get('time', '60.0')
                time_val = float(time_str.split(':')[-1]) if ':' in time_str else float(time_str)
                features['workout_quality'] = max(0, min(100, 100 - (time_val - 45) * 2))
            except (ValueError, TypeError):
                pass
        
        # Jockey and trainer stats
        jockey = horse_data.get('jockey', '')
        trainer = horse_data.get('trainer', '')
        
        if jockey in self.jockey_stats:
            stats = self.jockey_stats[jockey]
            features['jockey_win_rate_90d'] = stats['wins'] / stats['starts'] if stats['starts'] > 0 else 0.0
        
        if trainer in self.trainer_stats:
            stats = self.trainer_stats[trainer]
            features['trainer_win_rate_90d'] = stats['wins'] / stats['starts'] if stats['starts'] > 0 else 0.0
        
        # Distance and surface match (simplified)
        race_distance = race_info.get('distance', '')
        race_surface = race_info.get('surface', '').lower()
        
        if 'mile' in race_distance.lower():
            features['distance_match'] = 0.7
        elif 'furlong' in race_distance.lower():
            features['distance_match'] = 0.6
            
        if 'turf' in race_surface:
            features['surface_match'] = 0.8
        
        return features

    def _prepare_training_data(self) -> Tuple[pd.DataFrame, np.ndarray]:
        """Prepare feature matrix and target vector for training"""
        races = self._load_historical_data()
        self._calculate_jockey_trainer_stats(races)
        
        X = []
        y = []
        
        for race in races:
            race_info = {
                'distance': race.get('distance', ''),
                'surface': race.get('surface', '')
            }
            
            for horse in race.get('horses', []):
                horse_name = horse.get('name', '')
                if not horse_name:
                    continue
                    
                # Get horse data from historical records
                horse_data = next((h for h in races if h.get('name') == horse_name), {})
                
                # Extract features
                features = self._extract_features(horse_data, race_info)
                feature_vector = [features[f] for f in self.feature_names]
                
                # Target: finish position (1-10)
                finish_pos = horse.get('finish_position', 0)
                if 1 <= finish_pos <= 10:
                    X.append(feature_vector)
                    y.append(finish_pos)
        
        return pd.DataFrame(X, columns=self.feature_names), np.array(y)

    def train_model(self):
        """Train the XGBoost model with 5-fold cross-validation"""
        try:
            X, y = self._prepare_training_data()

            # Check if we have enough training data
            if len(X) == 0 or len(y) == 0:
                logger.warning("No training data available, initializing untrained model")
                self.model = XGBRegressor(
                    n_estimators=150,
                    max_depth=7,
                    learning_rate=0.05,
                    subsample=0.8,
                    colsample_bytree=0.9,
                    random_state=42,
                    eval_metric='mae'
                )
                return

            # Initialize model with racing-specific hyperparameters
            self.model = XGBRegressor(
                n_estimators=150,
                max_depth=7,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.9,
                random_state=42,
                eval_metric='mae'
            )

            # Only perform cross-validation if we have enough samples
            if len(X) >= 5:
                # Perform 5-fold cross-validation
                kf = KFold(n_splits=min(5, len(X)), shuffle=True, random_state=42)
                cv_scores = cross_val_score(self.model, X, y, cv=kf, scoring='neg_mean_absolute_error')
                mae_scores = -cv_scores
                logger.info(f"Cross-validation MAE: {mae_scores.mean():.2f} ± {mae_scores.std():.2f}")
            else:
                logger.warning(f"Only {len(X)} samples available, skipping cross-validation")

            # Train on full dataset
            self.model.fit(X, y)

            # Log feature importances
            importances = self.model.feature_importances_
            for feature, importance in zip(self.feature_names, importances):
                logger.debug(f"Feature '{feature}': {importance:.4f}")

        except Exception as e:
            logger.warning(f"Error training model: {e}, initializing untrained model")
            self.model = XGBRegressor(
                n_estimators=150,
                max_depth=7,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.9,
                random_state=42,
                eval_metric='mae'
            )

    def predict_finish_position(self, horse_data: Dict, race_info: Dict) -> float:
        """
        Predict finish position for a horse in a specific race
        
        Args:
            horse_data: Horse performance data
            race_info: Race conditions
            
        Returns:
            float: Predicted finish position (1-10 scale)
        """
        if not self.model:
            raise RuntimeError("Model not trained. Call train_model() first.")
            
        features = self._extract_features(horse_data, race_info)
        feature_vector = np.array([features[f] for f in self.feature_names]).reshape(1, -1)
        
        prediction = self.model.predict(feature_vector)[0]
        return max(1.0, min(10.0, prediction))

    def get_prediction_confidence(self, horse_data: Dict, race_info: Dict) -> float:
        """
        Calculate confidence score for a prediction (0-100)
        
        Returns:
            float: Confidence percentage
        """
        # Simplified confidence metric based on data availability
        confidence = 70.0  # Base confidence
        
        # Boost for available speed data
        if 'results' in horse_data and len(horse_data['results']) >= 3:
            confidence += 15.0
            
        # Boost for workout data
        if 'workouts' in horse_data and len(horse_data['workouts']) >= 1:
            confidence += 10.0
            
        # Boost for jockey/trainer data
        if horse_data.get('jockey') in self.jockey_stats:
            confidence += 5.0
        if horse_data.get('trainer') in self.trainer_stats:
            confidence += 5.0
            
        return min(100.0, confidence)