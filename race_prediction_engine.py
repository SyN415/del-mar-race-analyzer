#!/usr/bin/env python3
"""
Race Prediction Engine
Advanced algorithm for predicting horse race outcomes
Combines multiple factors: speed figures, workouts, class, odds, jockey/trainer stats
"""

import json
import statistics
import math
import os
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

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

class RacePredictionEngine:
    """Advanced prediction engine for horse racing"""

    def __init__(self):
        self.weight_factors = {
            'speed': 0.25,      # Speed figures (E column)
            'class': 0.15,      # Class of competition
            'form': 0.20,       # Recent form/consistency
            'workout': 0.15,    # Workout patterns
            'jockey': 0.08,     # Jockey performance
            'trainer': 0.07,    # Trainer statistics
            'equipment': 0.05,  # Equipment changes
            'pace': 0.03,       # Pace analysis
            'distance': 0.01,   # Distance suitability
            'surface': 0.01     # Surface preference
        }

        # Load realistic jockey and trainer data
        self.jockey_data = self.load_jockey_data()
        self.trainer_data = self.load_trainer_data()

    def load_jockey_data(self) -> Dict:
        """Load real jockey performance data only (no simulated sources)."""
        try:
            # Prefer explicit real scraped data
            if os.path.exists('real_equibase_jockey_data.json'):
                with open('real_equibase_jockey_data.json', 'r') as f:
                    return json.load(f)
            # Accept consolidated real DB if present
            if os.path.exists('real_jockey_trainer_database.json'):
                with open('real_jockey_trainer_database.json', 'r') as f:
                    data = json.load(f)
                    return data.get('jockeys', {})
            # Accept scraper DB output if used by equibase_jockey_scraper
            if os.path.exists('jockey_stats_database.json'):
                with open('jockey_stats_database.json', 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load jockey data: {e}")
        # No generated fallbacks; return empty to avoid fabricated analytics
        return {}

    def load_trainer_data(self) -> Dict:
        """Load real trainer performance data only (no simulated sources)."""
        try:
            if os.path.exists('real_equibase_trainer_data.json'):
                with open('real_equibase_trainer_data.json', 'r') as f:
                    return json.load(f)
            # Optional: accept a scraper DB if you have one (align naming like jockey)
            if os.path.exists('real_jockey_trainer_database.json'):
                with open('real_jockey_trainer_database.json', 'r') as f:
                    data = json.load(f)
                    return data.get('trainers', {})
            if os.path.exists('trainer_stats_database.json'):
                with open('trainer_stats_database.json', 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load trainer data: {e}")
        # No generated fallbacks; return empty to avoid fabricated analytics
        return {}

    def calculate_speed_rating(self, horse_data: Dict) -> float:
        """Calculate speed rating with SmartPick-aware OUR speed integration.
        Priority:
        1) If OUR speed is present (horse_data['our_speed_figure'] or horse_data['smartpick']['our_speed_figure']), use it
        2) Else if SmartPick best + last-3 are present, compute OUR = (best + avg_last3)/2
        3) Else fall back to recent Equibase results E figures (existing behavior)
        All speeds are assumed on the Equibase 'E' scale (~20–120) and normalized to 0–100.
        """
        # 1) Direct OUR speed value if already merged
        try:
            sp = horse_data.get('smartpick', {}) if isinstance(horse_data, dict) else {}
        except Exception:
            sp = {}
        our_speed = None
        # Allow either top-level or nested under 'smartpick'
        if isinstance(horse_data, dict) and isinstance(horse_data.get('our_speed_figure'), (int, float)):
            our_speed = float(horse_data['our_speed_figure'])
        elif isinstance(sp, dict):
            cand = sp.get('our_speed_figure') or sp.get('ourSpeedFigure')
            if isinstance(cand, (int, float)):
                our_speed = float(cand)
        # 2) Compute OUR from SmartPick components if available
        if our_speed is None and isinstance(sp, dict):
            best = sp.get('best_speed_figure') or sp.get('bestSpeedFigure')
            # last-3 can be provided as list or pre-averaged
            last3_list = sp.get('last_3_speeds') or sp.get('last3_speeds') or sp.get('last3E')
            avg_last3 = sp.get('avg_last_3_speed') or sp.get('avgLast3Speed')
            if isinstance(last3_list, list) and last3_list:
                try:
                    nums = [float(x) for x in last3_list if isinstance(x, (int, float))]
                    if nums:
                        avg_last3 = sum(nums) / len(nums)
                except Exception:
                    pass
            if isinstance(best, (int, float)) and isinstance(avg_last3, (int, float)):
                our_speed = (float(best) + float(avg_last3)) / 2.0
            elif isinstance(best, (int, float)):
                our_speed = float(best)
        # If we have OUR speed, normalize and return
        if isinstance(our_speed, (int, float)) and our_speed > 0:
            return max(0, min(100, (our_speed - 20.0) * 1.25))

        # 3) Fallback: recent Equibase results E figures
        results = horse_data.get('results', []) if isinstance(horse_data, dict) else []
        if not results:
            return 50.0  # Default neutral rating

        # Get recent speed scores (E column)
        recent_speeds = []
        for result in results[:10]:  # Last 10 races
            try:
                speed_score = result.get('speed_score', 0)
            except AttributeError:
                speed_score = 0
            if isinstance(speed_score, (int, float)) and speed_score > 0:
                recent_speeds.append(float(speed_score))

        if not recent_speeds:
            return 50.0

        # Calculate weighted average (more recent races weighted higher)
        weighted_sum = 0.0
        weight_total = 0.0
        for i, speed in enumerate(recent_speeds):
            weight = 1.0 / (i + 1)  # Decreasing weight for older races
            weighted_sum += speed * weight
            weight_total += weight

        avg_speed = weighted_sum / weight_total if weight_total > 0 else 50.0

        # Normalize to 0-100 scale (typical speed figures range 20-120)
        normalized = max(0, min(100, (avg_speed - 20) * 1.25))
        return normalized

    def calculate_class_rating(self, horse_data: Dict, race_info: Dict) -> float:
        """Calculate class rating based on competition level"""
        results = horse_data.get('results', [])
        current_race_type = race_info.get('race_type', '').upper()

        if not results:
            return 50.0

        # Analyze recent competition levels
        class_scores = []
        for result in results[:8]:  # Recent races
            # This would be enhanced with actual race type data
            # For now, use finish position as proxy for class
            finish_pos = result.get('finish_position', 10)
            if finish_pos > 0:
                # Better finishes in recent races = higher class rating
                class_score = max(0, 100 - (finish_pos - 1) * 10)
                class_scores.append(class_score)

        if not class_scores:
            return 50.0

        base_rating = statistics.mean(class_scores)

        # Adjust for current race type
        if 'MAIDEN' in current_race_type:
            base_rating *= 0.9  # Slightly lower for maiden races
        elif 'STAKES' in current_race_type:
            base_rating *= 1.1  # Higher for stakes races

        return min(100, max(0, base_rating))

    def calculate_form_rating(self, horse_data: Dict) -> float:
        """Calculate form rating based on recent consistency"""
        results = horse_data.get('results', [])
        if len(results) < 3:
            return 50.0

        recent_results = results[:6]  # Last 6 races
        form_points = 0
        total_races = len(recent_results)

        for i, result in enumerate(recent_results):
            finish_pos = result.get('finish_position', 10)
            if finish_pos > 0:
                # Points based on finish position (1st=10pts, 2nd=8pts, etc.)
                points = max(0, 11 - finish_pos)
                # Weight recent races more heavily
                weight = 1.0 - (i * 0.1)
                form_points += points * weight

        # Normalize to 0-100 scale
        max_possible = sum(10 * (1.0 - i * 0.1) for i in range(total_races))
        form_rating = (form_points / max_possible) * 100 if max_possible > 0 else 50.0

        return min(100, max(0, form_rating))

    def calculate_workout_rating(self, horse_data: Dict) -> float:
        """Calculate workout rating based on recent training"""
        workouts = horse_data.get('workouts', [])
        if not workouts:
            return 50.0

        recent_workouts = workouts[:5]  # Last 5 workouts
        workout_scores = []

        for workout in recent_workouts:
            distance = workout.get('distance', '')
            time_str = workout.get('time', '')
            workout_type = workout.get('workout_type', '')

            # Parse workout time and distance
            if distance and time_str:
                score = self.evaluate_workout_time(distance, time_str, workout_type)
                if score > 0:
                    workout_scores.append(score)

        if not workout_scores:
            return 50.0

        # Recent workouts weighted more heavily
        weighted_sum = 0
        weight_total = 0

        for i, score in enumerate(workout_scores):
            weight = 1.0 / (i + 1)
            weighted_sum += score * weight
            weight_total += weight

        avg_workout = weighted_sum / weight_total if weight_total > 0 else 50.0
        return min(100, max(0, avg_workout))

    def evaluate_workout_time(self, distance: str, time_str: str, workout_type: str) -> float:
        """Evaluate workout time quality"""
        # Standard workout time benchmarks (in seconds)
        benchmarks = {
            '4f': 48.0,   # 4 furlongs
            '5f': 60.0,   # 5 furlongs
            '6f': 72.0,   # 6 furlongs
            '3f': 36.0    # 3 furlongs
        }

        # Parse time string (format like "1:12.40" or "48.20")
        try:
            if ':' in time_str:
                parts = time_str.split(':')
                minutes = int(parts[0])
                seconds = float(parts[1])
                total_seconds = minutes * 60 + seconds
            else:
                total_seconds = float(time_str)
        except:
            return 50.0

        # Get benchmark for distance
        benchmark = benchmarks.get(distance, 60.0)

        # Calculate rating (faster than benchmark = higher rating)
        if total_seconds > 0:
            ratio = benchmark / total_seconds
            rating = ratio * 50 + 25  # Scale to 0-100

            # Adjust for workout type
            if 'b' in workout_type.lower():  # Breeze
                rating *= 1.1
            elif 'h' in workout_type.lower():  # Handily
                rating *= 1.05

            return min(100, max(0, rating))

        return 50.0

    def calculate_jockey_trainer_ratings(self, horse_data: Dict, jockey_name: str = "", trainer_name: str = "") -> Tuple[float, float]:
        """Calculate jockey and trainer ratings using real data when available.
        Supports both flat mappings {name: {...}} and consolidated DBs with keys 'jockeys'/'trainers'.
        If only win_percentage is present, derives a rating from it.
        """

        def derive_rating(rec: Dict, default: float) -> float:
            # Prefer explicit rating
            if rec is None:
                return default
            if isinstance(rec, dict):
                if 'rating' in rec and isinstance(rec['rating'], (int, float)):
                    return float(rec['rating'])
                win_pct = rec.get('win_percentage') or rec.get('overall_win_percentage')
                if isinstance(win_pct, (int, float)):
                    # Map win% roughly to 30–90 scale (e.g., 10% -> 30, 25% -> 75)
                    return float(max(30.0, min(90.0, win_pct * 3.0)))
            return default

        # Jockey
        jockey_rating = 50.0
        if jockey_name:
            jd = self.jockey_data or {}
            rec = None
            if isinstance(jd, dict):
                if 'jockeys' in jd and isinstance(jd['jockeys'], dict):
                    rec = jd['jockeys'].get(jockey_name)
                else:
                    rec = jd.get(jockey_name)
            jockey_rating = derive_rating(rec, jockey_rating)

        # Trainer
        trainer_rating = 50.0
        if trainer_name:
            td = self.trainer_data or {}
            trec = None
            if isinstance(td, dict):
                if 'trainers' in td and isinstance(td['trainers'], dict):
                    trec = td['trainers'].get(trainer_name)
                else:
                    trec = td.get(trainer_name)
            trainer_rating = derive_rating(trec, trainer_rating)

        return jockey_rating, trainer_rating

    def calculate_equipment_rating(self, equipment_changes: str) -> float:
        """Calculate rating adjustment for equipment/med changes"""
        rating = 50.0  # Neutral base
        if not equipment_changes:
            return rating
        changes = equipment_changes.lower()
        # Blinkers: positive in sprints/juveniles generally
        if 'blinkers on' in changes:
            rating += 5
        elif 'blinkers off' in changes:
            # Treat Blinkers Off as potential focus improvement rather than negative
            rating += 2
        # Tongue tie typically positive
        if 'tongue tie' in changes:
            rating += 2
        # First-time Lasix (L1) — strong angle in maiden claimers
        if 'l1' in changes or 'first time lasix' in changes or 'lasix' in changes:
            rating += 5
        return min(100, max(0, rating))

    def calculate_pace_rating(self, horse_data: Dict, race_info: Dict) -> float:
        """Calculate pace rating based on running style and race shape"""
        # Simplified pace analysis
        # Would be enhanced with actual pace figures and race shape analysis
        return 50.0

    def calculate_distance_surface_ratings(self, horse_data: Dict, race_info: Dict) -> Tuple[float, float]:
        """Calculate distance and surface suitability ratings"""
        results = horse_data.get('results', [])
        race_distance = race_info.get('distance', '')
        race_surface = race_info.get('surface', '').lower()

        distance_rating = 50.0
        surface_rating = 50.0

        if results:
            # Analyze performance at similar distances and surfaces
            similar_distance_results = []
            surface_results = []

            for result in results:
                result_distance = result.get('distance', '')
                result_surface = result.get('surface', '').lower()
                finish_pos = result.get('finish_position', 10)

                # Distance analysis (simplified)
                if result_distance and finish_pos > 0:
                    if race_distance in result_distance or result_distance in race_distance:
                        performance_score = max(0, 11 - finish_pos) * 10
                        similar_distance_results.append(performance_score)

                # Surface analysis
                if result_surface and finish_pos > 0:
                    if race_surface in result_surface:
                        performance_score = max(0, 11 - finish_pos) * 10
                        surface_results.append(performance_score)

            if similar_distance_results:
                distance_rating = statistics.mean(similar_distance_results)

            if surface_results:
                surface_rating = statistics.mean(surface_results)

        return min(100, max(0, distance_rating)), min(100, max(0, surface_rating))

    def calculate_composite_rating(self, factors: PredictionFactors) -> float:
        """Calculate final composite rating from all factors"""
        composite = (
            factors.speed_rating * self.weight_factors['speed'] +
            factors.class_rating * self.weight_factors['class'] +
            factors.form_rating * self.weight_factors['form'] +
            factors.workout_rating * self.weight_factors['workout'] +
            factors.jockey_rating * self.weight_factors['jockey'] +
            factors.trainer_rating * self.weight_factors['trainer'] +
            factors.equipment_rating * self.weight_factors['equipment'] +
            factors.pace_rating * self.weight_factors['pace'] +
            factors.distance_rating * self.weight_factors['distance'] +
            factors.surface_rating * self.weight_factors['surface']
        )
        return min(100, max(0, composite))

    # --------------------------- Contextual Heuristics ---------------------------
    def _parse_ml_fraction(self, ml: str) -> Optional[Tuple[int, int]]:
        if not ml:
            return None
        try:
            if '/' in ml:
                a, b = ml.strip().split('/')
                return int(a), int(b)
        except Exception:
            return None
        return None

    def _distance_flags(self, distance: str, surface: str) -> Dict[str, bool]:
        d = distance.lower()
        s = surface.lower()
        return {
            'is_5f': ('5' in d and 'furlong' in d) and not ('6 1/2' in d or '6.5' in d),
            'is_6_5f': ('6 1/2' in d) or ('6.5' in d),
            'is_7f': ('7' in d and 'furlong' in d),
            'is_route': ('mile' in d and not ('7' in d and 'furlong' in d)),
            'is_turf': s == 'turf',
            'is_dirt': s == 'dirt',
        }

    def _context_bonus(self, horse: Dict, race_info: Dict, total_horses: int) -> float:
        """Add contextual bonus/penalty based on Del Mar insights (bounded)."""
        bonus = 0.0
        surface = race_info.get('surface', '')
        distance = race_info.get('distance', '')
        race_type = race_info.get('race_type', '')
        flags = self._distance_flags(distance, surface)
        post = int(horse.get('post_position', 0) or 0)
        jockey = (horse.get('jockey') or '').strip()
        trainer = (horse.get('trainer') or '').strip()
        ml = horse.get('morning_line_odds', '')
        ml_frac = self._parse_ml_fraction(ml)

        # Rider/barn sets
        TURF_SPRINT_JOCKEYS = {'K Kimura', 'U Rispoli', 'M E Smith', 'J J Hernandez', 'H I Berrios'}
        TOP_TURF_ROUTE_RIDERS = {'M Demuro', 'U Rispoli', 'J J Hernandez'}
        HOT_RIDERS = {'K Kimura', 'U Rispoli', 'H I Berrios', 'A Fresu', 'J J Hernandez'}
        HOT_BARNS = {'J Mullins', 'P Miller', 'M Glatt', 'J W Sadler', 'R B Hess, Jr.'}

        # 5f Turf sprint: inside/mid posts; turf-sprint riders
        if flags['is_5f'] and flags['is_turf']:
            if 1 <= post <= 3:
                bonus += 3.0
            elif 4 <= post <= 5:
                bonus += 1.5
            elif post >= 8:
                bonus -= 2.0
            if jockey in TURF_SPRINT_JOCKEYS:
                bonus += 1.5

        # Turf routes (mile+): inside draw tempered; course-craft riders
        if flags['is_route'] and flags['is_turf']:
            if 1 <= post <= 3:
                bonus += 2.0
            if jockey in TOP_TURF_ROUTE_RIDERS:
                bonus += 1.5
            # 3yo vs older penalty in AOC turf routes
            age = horse.get('age')
            if age == 3 and 'ALLOWANCE OPTIONAL CLAIMING' in race_type.upper():
                bonus -= 1.5

        # Dirt mile claimers/OC: stalker/mid-post, heat index (approx via rider/barn lists)
        if flags['is_route'] and flags['is_dirt']:
            if total_horses >= 6 and 3 <= post <= max(4, total_horses - 2):
                bonus += 1.5
            if (jockey in HOT_RIDERS) and (trainer in HOT_BARNS):
                bonus += 1.0

        # 6.5f dirt at DMR favors mid posts
        if flags['is_6_5f'] and flags['is_dirt']:
            if total_horses >= 6 and 3 <= post <= max(4, total_horses - 2):
                bonus += 1.0

        # 7f dirt: inside/mid slight bump
        if flags['is_7f'] and flags['is_dirt']:
            if 1 <= post <= 5:
                bonus += 1.0

        # N2L chalk penalty
        cond = (race_info.get('conditions', '') or '').upper()
        if ('NEVER WON TWO' in cond or 'N2L' in cond) and ml_frac:
            a, b = ml_frac
            if b > 0 and (a / b) <= 2:  # 2/1 or lower ML
                bonus -= 1.0

        # Bound bonus to avoid overpowering base model
        return max(-5.0, min(5.0, bonus))

        return min(100, max(0, composite))

    def predict_race(self, race_data: Dict, horse_data_collection: Dict) -> Dict:
        """Generate comprehensive race predictions"""
        horses = race_data.get('horses', [])
        race_info = {
            'race_type': race_data.get('race_type', ''),
            'distance': race_data.get('distance', ''),
            'surface': race_data.get('surface', ''),
            'conditions': race_data.get('conditions', ''),
        }

        horse_predictions = []
        total_horses = len(horses)

        for horse in horses:
            horse_name = horse.get('name', '')
            horse_data = horse_data_collection.get(horse_name, {})

            # Calculate all rating factors
            factors = PredictionFactors()
            factors.speed_rating = self.calculate_speed_rating(horse_data)
            factors.class_rating = self.calculate_class_rating(horse_data, race_info)
            factors.form_rating = self.calculate_form_rating(horse_data)
            factors.workout_rating = self.calculate_workout_rating(horse_data)
            factors.jockey_rating, factors.trainer_rating = self.calculate_jockey_trainer_ratings(
                horse_data, horse.get('jockey', ''), horse.get('trainer', ''))
            factors.equipment_rating = self.calculate_equipment_rating(horse.get('equipment_changes', ''))
            factors.pace_rating = self.calculate_pace_rating(horse_data, race_info)
            factors.distance_rating, factors.surface_rating = self.calculate_distance_surface_ratings(horse_data, race_info)

            # Calculate composite rating + contextual bonus
            base = self.calculate_composite_rating(factors)
            bonus = self._context_bonus(horse, race_info, total_horses)
            composite_rating = min(100.0, max(0.0, base + bonus))

            horse_prediction = {
                'name': horse_name,
                'post_position': horse.get('post_position', 0),
                'jockey': horse.get('jockey', ''),
                'trainer': horse.get('trainer', ''),
                'age': horse.get('age'),
                'morning_line': horse.get('morning_line_odds', ''),
                'composite_rating': round(composite_rating, 2),
                'factors': {
                    'speed': round(factors.speed_rating, 1),
                    'class': round(factors.class_rating, 1),
                    'form': round(factors.form_rating, 1),
                    'workout': round(factors.workout_rating, 1),
                    'jockey': round(factors.jockey_rating, 1),
                    'trainer': round(factors.trainer_rating, 1),
                    'equipment': round(factors.equipment_rating, 1)
                }
            }

            horse_predictions.append(horse_prediction)

        # Sort by composite rating
        horse_predictions.sort(key=lambda x: x['composite_rating'], reverse=True)

        # Calculate win probabilities
        total_rating = sum(h['composite_rating'] for h in horse_predictions) or 1.0
        for horse_pred in horse_predictions:
            probability = (horse_pred['composite_rating'] / total_rating) * 100
            horse_pred['win_probability'] = round(probability, 1)

        return {
            'race_number': race_data.get('race_number', 0),
            'race_type': race_data.get('race_type', ''),
            'distance': race_data.get('distance', ''),
            'surface': race_data.get('surface', ''),
            'predictions': horse_predictions,
            'top_pick': horse_predictions[0] if horse_predictions else None,
            'exotic_suggestions': self.generate_exotic_suggestions(horse_predictions)
        }

    def generate_exotic_suggestions(self, predictions: List[Dict]) -> Dict:
        """Generate exotic bet suggestions based on predictions"""
        if len(predictions) < 2:
            return {}

        top_4_positions = [p['post_position'] for p in predictions[:4]]

        return {
            'win': top_4_positions[0],
            'exacta': f"{top_4_positions[0]}-{top_4_positions[1]}",
            'exacta_box': f"{top_4_positions[0]},{top_4_positions[1]}",
            'trifecta': f"{top_4_positions[0]}-{top_4_positions[1]}-{top_4_positions[2]}" if len(top_4_positions) >= 3 else "",
            'trifecta_box': f"{top_4_positions[0]},{top_4_positions[1]},{top_4_positions[2]}" if len(top_4_positions) >= 3 else "",
            'superfecta': f"{top_4_positions[0]}-{top_4_positions[1]}-{top_4_positions[2]}-{top_4_positions[3]}" if len(top_4_positions) >= 4 else ""
        }

def main():
    """Example usage of the prediction engine"""
    engine = RacePredictionEngine()

    # Example race data structure
    sample_race = {
        'race_number': 1,
        'race_type': 'MAIDEN CLAIMING',
        'distance': '1 Mile',
        'surface': 'Turf',
        'horses': [
            {'name': 'Little Silver Girl', 'post_position': 1, 'jockey': 'A Escobedo', 'trainer': 'R Hanson', 'morning_line_odds': '20/1'},
            {'name': 'Goatski', 'post_position': 2, 'jockey': 'H I Berrios', 'trainer': 'D Blacker', 'morning_line_odds': '7/5'},
            {'name': 'Honey Jo', 'post_position': 5, 'jockey': 'A Fresu', 'trainer': 'P Eurton', 'morning_line_odds': '3/1', 'equipment_changes': 'Blinkers On'}
        ]
    }

    # Example horse data (would come from scraper)
    sample_horse_data = {
        'Goatski': {
            'results': [
                {'speed_score': 85, 'finish_position': 2, 'surface': 'turf'},
                {'speed_score': 82, 'finish_position': 3, 'surface': 'turf'}
            ],
            'workouts': [
                {'distance': '4f', 'time': '47.80', 'workout_type': 'b'}
            ]
        }
    }

    predictions = engine.predict_race(sample_race, sample_horse_data)
    print(json.dumps(predictions, indent=2))

if __name__ == "__main__":
    main()
