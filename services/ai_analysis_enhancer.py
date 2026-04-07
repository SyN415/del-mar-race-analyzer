#!/usr/bin/env python3
"""
AI Analysis Enhancer Service
Provides AI-powered prediction refinement with confidence levels,
risk analysis, pattern recognition, and strategic insights
"""

import asyncio
import json
import logging
import statistics
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

from services.openrouter_client import OpenRouterClient

logger = logging.getLogger(__name__)

class ConfidenceLevel(Enum):
    """Confidence levels for predictions"""
    VERY_LOW = "very_low"      # 0-20%
    LOW = "low"                # 20-40%
    MODERATE = "moderate"      # 40-60%
    HIGH = "high"              # 60-80%
    VERY_HIGH = "very_high"    # 80-100%

class RiskLevel(Enum):
    """Risk levels for betting recommendations"""
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"
    SPECULATIVE = "speculative"

@dataclass
class AnalysisInsight:
    """Individual analysis insight"""
    category: str
    insight: str
    confidence: float
    impact_level: str
    supporting_data: Dict

class AIAnalysisEnhancer:
    """AI-powered analysis enhancement with pattern recognition"""

    # Default track takeout rates for exotic pools (used in EV calculations)
    DEFAULT_TAKEOUT = {
        "exacta": 0.2060,
        "trifecta": 0.2364,
        "superfecta": 0.2364,
    }

    def __init__(self, openrouter_client: OpenRouterClient):
        self.ai_client = openrouter_client
        self.historical_patterns: Dict[str, List[Dict]] = {}
        self.track_biases: Dict[str, Dict] = {}
        self.jockey_trainer_insights: Dict[str, Dict] = {}

    # ── Harville helpers & odds parsing ─────────────────────────────────

    @staticmethod
    def _parse_ml_odds(odds_str: Optional[str]) -> float:
        """Convert a morning-line odds string (e.g. '5-2', '3/1', '8.0')
        to *decimal* odds (e.g. 3.5, 4.0, 8.0).  Returns 0.0 on failure."""
        if not odds_str:
            return 0.0
        s = str(odds_str).strip()
        import re
        # fractional with dash or slash: "5-2", "3/1"
        m = re.match(r'^(\d+(?:\.\d+)?)\s*[-/]\s*(\d+(?:\.\d+)?)$', s)
        if m:
            num, den = float(m.group(1)), float(m.group(2))
            if den == 0:
                return 0.0
            return (num / den) + 1.0
        # plain decimal or integer
        try:
            val = float(s)
            return val if val > 0 else 0.0
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _implied_probability(decimal_odds: float) -> float:
        """Implied win probability from decimal odds (no vig adjustment)."""
        if decimal_odds <= 1.0:
            return 1.0
        return 1.0 / decimal_odds

    @staticmethod
    def _harville_exacta_prob(p_a: float, p_b: float) -> float:
        """Harville model: P(A finishes 1st AND B finishes 2nd).
        Formula: P(A) × P(B) / (1 − P(A))"""
        if p_a >= 1.0 or p_a <= 0.0:
            return 0.0
        return p_a * (p_b / (1.0 - p_a))

    @staticmethod
    def _harville_trifecta_prob(p_a: float, p_b: float, p_c: float) -> float:
        """Harville model: P(A 1st, B 2nd, C 3rd).
        Formula: P(A) × [P(B)/(1−P(A))] × [P(C)/(1−P(A)−P(B))]"""
        if p_a >= 1.0 or p_a <= 0.0:
            return 0.0
        denom_b = 1.0 - p_a
        if denom_b <= 0:
            return 0.0
        denom_c = 1.0 - p_a - p_b
        if denom_c <= 0:
            return 0.0
        return p_a * (p_b / denom_b) * (p_c / denom_c)

    @staticmethod
    def _prelec_weight(p: float, beta: float = 0.9) -> float:
        """Prelec probability weighting function (Prelec 1998).
        Corrects for favorite-longshot bias: overweights small probabilities
        (longshots) and underweights large ones (favorites).
        π(p) = exp(−(−ln(p))^β), β≈0.9 per empirical racing research."""
        import math
        if p <= 0.0:
            return 0.0
        if p >= 1.0:
            return 1.0
        return math.exp(-((-math.log(p)) ** beta))

    @staticmethod
    def _harville_exacta_prob_discounted(p_a: float, p_b: float, discount: float = 0.85) -> float:
        """Discounted Harville exacta: applies discount factor to 2nd-place term.
        Reduces overestimation of longshot ordering probability."""
        if p_a >= 1.0 or p_a <= 0.0:
            return 0.0
        denom = 1.0 - p_a
        if denom <= 0:
            return 0.0
        return p_a * (p_b / denom) * discount

    @staticmethod
    def _harville_trifecta_prob_discounted(p_a: float, p_b: float, p_c: float, discount: float = 0.85) -> float:
        """Discounted Harville trifecta: applies discount to both 2nd and 3rd terms."""
        if p_a >= 1.0 or p_a <= 0.0:
            return 0.0
        denom_b = 1.0 - p_a
        if denom_b <= 0:
            return 0.0
        denom_c = 1.0 - p_a - p_b
        if denom_c <= 0:
            return 0.0
        return p_a * (p_b / denom_b) * discount * (p_c / denom_c) * discount
        
    async def enhance_race_analysis(self, race_data: Dict, horse_predictions: List[Dict],
                                  historical_data: Dict = None,
                                  model_override: Optional[str] = None) -> Dict:
        """
        Enhance race analysis with AI insights and confidence scoring

        Args:
            race_data: Race information (distance, surface, conditions, etc.)
            horse_predictions: Initial algorithmic predictions
            historical_data: Historical performance data if available
            model_override: Explicit model to use for AI calls (user selection)

        Returns:
            Enhanced analysis with AI insights and confidence scores
        """
        # Prepare comprehensive analysis context
        analysis_context = {
            "race_info": race_data,
            "field_analysis": self._analyze_field_strength(horse_predictions),
            "top_contenders": horse_predictions[:5],
            "historical_context": historical_data or {},
            "track_conditions": self._extract_track_conditions(race_data)
        }
        
        # Get AI-powered enhancement (with user's model selection)
        logger.info(
            "🤖 AI enhance_race_analysis | model_override=%s",
            model_override or "(auto-select)",
        )
        ai_enhancement = await self.ai_client.enhance_predictions(
            race_data,
            horse_predictions,
            horse_predictions,
            model_override=model_override,
        )
        
        # Generate confidence scores
        confidence_analysis = self._generate_confidence_scores(horse_predictions, ai_enhancement)
        
        # Identify value opportunities
        value_analysis = self._identify_value_opportunities(horse_predictions, confidence_analysis)
        
        # Risk assessment
        risk_analysis = self._assess_betting_risks(horse_predictions, race_data)
        
        # Pattern recognition
        pattern_insights = await self._recognize_patterns(race_data, horse_predictions)
        
        enhanced_analysis = {
            "original_predictions": horse_predictions,
            "ai_enhancement": ai_enhancement,
            "confidence_analysis": confidence_analysis,
            "value_opportunities": value_analysis,
            "risk_assessment": risk_analysis,
            "pattern_insights": pattern_insights,
            "recommended_strategy": self._generate_betting_strategy(
                horse_predictions, confidence_analysis, value_analysis, risk_analysis
            ),
            "enhancement_timestamp": time.time()
        }
        
        # Store insights for future pattern recognition
        self._store_analysis_patterns(race_data, enhanced_analysis)
        
        return enhanced_analysis
    
    def _analyze_field_strength(self, predictions: List[Dict]) -> Dict:
        """Analyze overall field strength and competitiveness"""
        if not predictions or len(predictions) < 3:
            return {"strength": "insufficient_data", "competitiveness": "unknown"}
        
        ratings = [p.get('composite_rating', 0) for p in predictions]
        win_probs = [p.get('win_probability', 0) for p in predictions]
        
        # Calculate field metrics
        rating_spread = max(ratings) - min(ratings) if ratings else 0
        top_3_spread = ratings[0] - ratings[2] if len(ratings) > 2 else 0
        avg_rating = statistics.mean(ratings) if ratings else 0
        
        # Assess field strength
        if avg_rating > 85:
            strength = "very_strong"
        elif avg_rating > 75:
            strength = "strong"
        elif avg_rating > 65:
            strength = "moderate"
        else:
            strength = "weak"
        
        # Assess competitiveness
        if top_3_spread < 5:
            competitiveness = "very_competitive"
        elif top_3_spread < 10:
            competitiveness = "competitive"
        elif top_3_spread < 20:
            competitiveness = "moderate"
        else:
            competitiveness = "clear_favorite"
        
        return {
            "strength": strength,
            "competitiveness": competitiveness,
            "rating_spread": rating_spread,
            "top_3_spread": top_3_spread,
            "average_rating": avg_rating,
            "field_size": len(predictions)
        }
    
    def _generate_confidence_scores(self, predictions: List[Dict], ai_enhancement: Dict) -> Dict:
        """Generate confidence scores for each prediction"""
        confidence_scores = {}
        
        for i, prediction in enumerate(predictions[:5]):  # Top 5 horses
            horse_name = prediction.get('horse_name', f'Horse_{i+1}')
            
            # Base confidence from algorithmic rating
            base_confidence = min(prediction.get('composite_rating', 0) / 100, 1.0)
            
            # Adjust based on win probability
            prob_confidence = prediction.get('win_probability', 0) / 100
            
            # Factor in field position
            position_factor = max(0.2, 1.0 - (i * 0.15))  # Decrease confidence for lower positions
            
            # AI enhancement factor
            ai_boost = 0.1 if ai_enhancement.get('confidence_boost', False) else 0
            
            # Calculate final confidence
            final_confidence = min(
                (base_confidence * 0.4 + prob_confidence * 0.4 + position_factor * 0.2) + ai_boost,
                1.0
            )
            
            # Categorize confidence level
            if final_confidence >= 0.8:
                level = ConfidenceLevel.VERY_HIGH
            elif final_confidence >= 0.6:
                level = ConfidenceLevel.HIGH
            elif final_confidence >= 0.4:
                level = ConfidenceLevel.MODERATE
            elif final_confidence >= 0.2:
                level = ConfidenceLevel.LOW
            else:
                level = ConfidenceLevel.VERY_LOW
            
            confidence_scores[horse_name] = {
                "score": final_confidence,
                "level": level.value,
                "factors": {
                    "algorithmic_rating": base_confidence,
                    "win_probability": prob_confidence,
                    "field_position": position_factor,
                    "ai_enhancement": ai_boost
                }
            }
        
        return confidence_scores
    
    def _identify_value_opportunities(self, predictions: List[Dict], confidence_analysis: Dict) -> List[Dict]:
        """Identify potential value betting opportunities"""
        value_opportunities = []
        
        for prediction in predictions:
            horse_name = prediction.get('horse_name', '')
            if not horse_name or horse_name not in confidence_analysis:
                continue
            
            confidence = confidence_analysis[horse_name]['score']
            win_prob = prediction.get('win_probability', 0)
            composite_rating = prediction.get('composite_rating', 0)
            
            # Calculate value score (confidence vs expected odds)
            expected_odds = 100 / max(win_prob, 1)  # Convert probability to odds
            
            # Value exists when confidence is higher than implied probability
            value_score = confidence - (win_prob / 100)
            
            if value_score > 0.1:  # Significant value threshold
                value_opportunities.append({
                    "horse_name": horse_name,
                    "value_score": value_score,
                    "confidence": confidence,
                    "win_probability": win_prob,
                    "expected_odds": expected_odds,
                    "composite_rating": composite_rating,
                    "value_type": "overlay" if value_score > 0.2 else "mild_value"
                })
        
        # Sort by value score
        return sorted(value_opportunities, key=lambda x: x['value_score'], reverse=True)
    
    def _assess_betting_risks(self, predictions: List[Dict], race_data: Dict) -> Dict:
        """Assess betting risks for the race"""
        field_analysis = self._analyze_field_strength(predictions)
        
        # Risk factors
        risk_factors = []
        overall_risk = RiskLevel.MODERATE
        
        # Field competitiveness risk
        if field_analysis['competitiveness'] == 'very_competitive':
            risk_factors.append("Highly competitive field - outcomes unpredictable")
            overall_risk = RiskLevel.AGGRESSIVE
        elif field_analysis['competitiveness'] == 'clear_favorite':
            risk_factors.append("Clear favorite present - limited value in win pool")
        
        # Distance and surface risks
        distance = race_data.get('distance', '')
        surface = race_data.get('surface', '')
        
        if 'sprint' in distance.lower() or '5' in distance or '6' in distance:
            risk_factors.append("Sprint distance - pace and break crucial")
        elif 'mile' in distance.lower() and ('half' in distance.lower() or '1.5' in distance):
            risk_factors.append("Long distance - stamina and pace distribution key")
        
        if 'turf' in surface.lower():
            risk_factors.append("Turf surface - weather and course bias important")
        
        # Field size risk
        field_size = len(predictions)
        if field_size > 12:
            risk_factors.append("Large field - increased chance of longshot winner")
            if overall_risk == RiskLevel.MODERATE:
                overall_risk = RiskLevel.AGGRESSIVE
        elif field_size < 6:
            risk_factors.append("Small field - limited betting value")
            if overall_risk == RiskLevel.AGGRESSIVE:
                overall_risk = RiskLevel.MODERATE
        
        return {
            "overall_risk": overall_risk.value,
            "risk_factors": risk_factors,
            "recommended_approach": self._get_risk_approach(overall_risk),
            "bankroll_allocation": self._get_bankroll_recommendation(overall_risk)
        }
    
    def _get_risk_approach(self, risk_level: RiskLevel) -> str:
        """Get recommended approach based on risk level"""
        approaches = {
            RiskLevel.CONSERVATIVE: "Focus on Win/Place bets on top choices",
            RiskLevel.MODERATE: "Balanced approach with some exotic betting",
            RiskLevel.AGGRESSIVE: "Consider exotic bets and value plays",
            RiskLevel.SPECULATIVE: "Small stakes on longshots and complex exotics"
        }
        return approaches.get(risk_level, "Balanced approach")
    
    def _get_bankroll_recommendation(self, risk_level: RiskLevel) -> Dict:
        """Get bankroll allocation recommendation"""
        allocations = {
            RiskLevel.CONSERVATIVE: {"win_place": 0.8, "show": 0.15, "exotic": 0.05},
            RiskLevel.MODERATE: {"win_place": 0.6, "show": 0.2, "exotic": 0.2},
            RiskLevel.AGGRESSIVE: {"win_place": 0.4, "show": 0.1, "exotic": 0.5},
            RiskLevel.SPECULATIVE: {"win_place": 0.2, "show": 0.1, "exotic": 0.7}
        }
        return allocations.get(risk_level, allocations[RiskLevel.MODERATE])
    
    async def _recognize_patterns(self, race_data: Dict, predictions: List[Dict]) -> List[AnalysisInsight]:
        """Recognize patterns from historical data and current race"""
        insights = []
        
        # Track-specific patterns
        track_code = race_data.get('track_code', 'UNK')
        if track_code in self.track_biases:
            bias_data = self.track_biases[track_code]
            insights.append(AnalysisInsight(
                category="track_bias",
                insight=f"Track historically favors {bias_data.get('preferred_style', 'unknown')} runners",
                confidence=bias_data.get('confidence', 0.5),
                impact_level="medium",
                supporting_data=bias_data
            ))
        
        # Distance patterns
        distance = race_data.get('distance', '')
        if distance and predictions:
            top_horse = predictions[0]
            if 'sprint' in distance.lower():
                insights.append(AnalysisInsight(
                    category="distance_pattern",
                    insight="Sprint races favor early speed and tactical pace",
                    confidence=0.7,
                    impact_level="high",
                    supporting_data={"distance": distance, "top_horse": top_horse.get('horse_name')}
                ))
        
        return insights

    # ── Strategy 1: Consecutive-Ranking Exotic Grouping ─────────────────

    def _compute_exotic_grouping(self, predictions: List[Dict]) -> Optional[Dict]:
        """Strategy 1 — Ranking-adjacency exacta / trifecta.

        Trigger:  top pick win_probability >= 35 % AND composite_rating gap
                  to #2 >= 15 pts.
        Build:    Use *predicted finish order* (composite_rating rank) rather
                  than post positions.
        Output:   dict with exacta/trifecta combos plus Harville probabilities.
        """
        if len(predictions) < 3:
            return None

        top = predictions[0]
        second = predictions[1]
        third = predictions[2]

        win_prob = top.get('win_probability', 0.0)
        gap = top.get('composite_rating', 0) - second.get('composite_rating', 0)

        if win_prob < 35.0 or gap < 15.0:
            return None  # conviction threshold not met

        # Normalised probabilities for Harville
        p = [h.get('win_probability', 0) / 100.0 for h in predictions[:3]]

        exacta_prob = self._harville_exacta_prob_discounted(p[0], p[1])
        trifecta_prob = self._harville_trifecta_prob_discounted(p[0], p[1], p[2])

        return {
            "triggered": True,
            "trigger_reason": (
                f"{top.get('horse_name')} has {win_prob:.1f}% win prob "
                f"with {gap:.1f}pt gap to 2nd"
            ),
            "exacta": {
                "horses": [top.get('horse_name', ''), second.get('horse_name', '')],
                "harville_probability": round(exacta_prob, 4),
            },
            "trifecta": {
                "horses": [
                    top.get('horse_name', ''),
                    second.get('horse_name', ''),
                    third.get('horse_name', ''),
                ],
                "harville_probability": round(trifecta_prob, 4),
            },
            "conviction_level": "strong" if gap >= 18 else "moderate",
        }

    def _compute_longshot_flags(self, predictions: List[Dict]) -> List[Dict]:
        """Identify longshots with misperception-corrected positive EV.

        A longshot is flagged when ALL of:
          - morning_line_odds >= 10-1 (decimal >= 11.0)
          - Prelec-adjusted model probability exceeds ML-implied probability by >= 10%
          - Rating gap to the field leader is < 12 points (close enough to upset)
        """
        if len(predictions) < 2:
            return []
        flags: List[Dict] = []
        top_rating = predictions[0].get("composite_rating", 0)

        for pred in predictions:
            ml_str = pred.get("morning_line_odds", "")
            ml_dec = self._parse_ml_odds(ml_str)
            if ml_dec < 11.0:  # Not a longshot (10-1 = decimal 11.0)
                continue

            ml_implied = self._implied_probability(ml_dec)
            raw_prob = pred.get("win_probability", 0) / 100.0
            if raw_prob <= 0:
                continue

            prelec_adj = self._prelec_weight(raw_prob)
            rating_gap = top_rating - pred.get("composite_rating", 0)

            # Flag: Prelec-adjusted prob exceeds market by >= 10% AND within striking range
            if prelec_adj > ml_implied * 1.10 and rating_gap < 12.0:
                ev_signal = round((prelec_adj - ml_implied) / max(ml_implied, 0.001) * 100, 1)
                flags.append({
                    "horse_name": pred.get("horse_name", ""),
                    "morning_line": ml_str,
                    "ml_implied_prob_pct": round(ml_implied * 100, 1),
                    "prelec_adjusted_prob_pct": round(prelec_adj * 100, 1),
                    "ev_signal_pct": ev_signal,
                    "rating_gap_to_leader": round(rating_gap, 1),
                    "flag_summary": (
                        f"{pred.get('horse_name','')} at {ml_str}: model ({round(prelec_adj*100,1)}%) "
                        f"vs market ({round(ml_implied*100,1)}%) — +{ev_signal}% EV signal"
                    ),
                })

        return sorted(flags, key=lambda x: x["ev_signal_pct"], reverse=True)

    # ── Strategy 2: Upset Play with Favorite Hedge ──────────────────────

    def _compute_upset_hedge(self, predictions: List[Dict]) -> Optional[Dict]:
        """Strategy 2 — Heavy-favorite hedge.

        Detect:  'Heavy Favorite' = ML <= 2/1  **or**  win_probability gap
                 between #1 and #2 >= 20 pts.
        Select:  Upset candidate = horse ranked 3rd-6th whose composite rating
                 is within 8-15 pts of the favourite.
        Build:   Exacta with upset candidate on top and favourite underneath.
        """
        if len(predictions) < 4:
            return None

        fav = predictions[0]
        second = predictions[1]

        # Check if favourite qualifies as "heavy"
        ml_odds_str = fav.get('morning_line_odds', '')
        ml_decimal = self._parse_ml_odds(ml_odds_str)
        is_heavy_by_ml = 0 < ml_decimal <= 3.0   # 2/1 → decimal 3.0
        win_gap = fav.get('win_probability', 0) - second.get('win_probability', 0)
        is_heavy_by_gap = win_gap >= 20.0

        if not (is_heavy_by_ml or is_heavy_by_gap):
            return None

        fav_rating = fav.get('composite_rating', 0)

        # Find best upset candidate (ranked 3rd-6th, within 8-15 pts)
        upset_candidate = None
        for h in predictions[2:6]:
            diff = fav_rating - h.get('composite_rating', 0)
            if 8.0 <= diff <= 15.0:
                upset_candidate = h
                break

        if not upset_candidate:
            # Relax: pick closest horse in 3rd-6th within 18 pts
            for h in predictions[2:6]:
                diff = fav_rating - h.get('composite_rating', 0)
                if diff <= 18.0:
                    upset_candidate = h
                    break

        if not upset_candidate:
            return None

        # Harville probability for upset exacta (upset 1st, fav 2nd)
        p_upset = upset_candidate.get('win_probability', 0) / 100.0
        p_fav = fav.get('win_probability', 0) / 100.0
        upset_exacta_prob = self._harville_exacta_prob_discounted(p_upset, p_fav)

        return {
            "triggered": True,
            "heavy_favorite": {
                "horse": fav.get('horse_name', ''),
                "win_probability": fav.get('win_probability', 0),
                "morning_line": ml_odds_str or "N/A",
                "detection_method": "morning_line" if is_heavy_by_ml else "win_prob_gap",
            },
            "upset_candidate": {
                "horse": upset_candidate.get('horse_name', ''),
                "composite_rating": upset_candidate.get('composite_rating', 0),
                "rating_gap": round(fav_rating - upset_candidate.get('composite_rating', 0), 1),
            },
            "hedge_exacta": {
                "order": [upset_candidate.get('horse_name', ''), fav.get('horse_name', '')],
                "harville_probability": round(upset_exacta_prob, 4),
                "description": (
                    f"Key {upset_candidate.get('horse_name', '')} over "
                    f"{fav.get('horse_name', '')} in exacta"
                ),
            },
        }

    # ── Strategy 3: High-Odds Expected-Value Exotics ────────────────────

    def _compute_high_odds_value_exotics(
        self, predictions: List[Dict], takeout: Optional[Dict] = None
    ) -> List[Dict]:
        """Strategy 3 — EV-positive exotic combos.

        Compares MODEL probability (from composite-rating-derived win_probability)
        against MARKET probability (from morning_line_odds) to find overlays.

        For each exacta & trifecta permutation of the top-5 ranked horses:
            model_prob  = Harville(model win probs)
            market_prob = Harville(ML-implied win probs)
            est_payout  = (1 / market_prob) × (1 − takeout)
            EV = (model_prob × est_payout) − $1 stake

        Flag combos where EV ≥ 0.15 (15% edge over stake).
        Falls back to model-only probabilities when morning line is unavailable.
        """
        if len(predictions) < 3:
            return []

        tk = takeout or self.DEFAULT_TAKEOUT
        top_n = predictions[:5]

        # Model probabilities (from composite rating)
        model_probs = [h.get('win_probability', 0) / 100.0 for h in top_n]

        # Market probabilities (from morning line odds)
        ml_probs_raw = []
        for h in top_n:
            ml_str = h.get('morning_line_odds', '')
            ml_dec = self._parse_ml_odds(ml_str)
            ml_probs_raw.append(self._implied_probability(ml_dec) if ml_dec > 0 else 0.0)

        # If fewer than 2 horses have ML odds, fall back to a wider spread
        # by using model probs as the market estimate (no EV edge possible)
        has_ml = sum(1 for p in ml_probs_raw if p > 0)
        if has_ml < 2:
            # No meaningful market comparison — use model probs with a small
            # synthetic spread to still surface the widest-price combos
            market_probs = model_probs
        else:
            # Normalise ML-implied probs to sum to 1 across the subset
            ml_total = sum(ml_probs_raw) or 1.0
            market_probs = [(p / ml_total) if p > 0 else model_probs[i]
                           for i, p in enumerate(ml_probs_raw)]

        names = [h.get('horse_name', '') for h in top_n]
        ev_plays: List[Dict] = []

        # Exacta permutations
        for i in range(len(top_n)):
            for j in range(len(top_n)):
                if i == j:
                    continue
                model_p = self._harville_exacta_prob_discounted(model_probs[i], model_probs[j])
                market_p = self._harville_exacta_prob(market_probs[i], market_probs[j])
                if model_p <= 0 or market_p <= 0:
                    continue
                est_payout = (1.0 / market_p) * (1.0 - tk.get("exacta", 0.206))
                ev = (model_p * est_payout) - 1.0
                if ev >= 0.18:
                    ev_plays.append({
                        "bet_type": "exacta",
                        "horses": [names[i], names[j]],
                        "harville_probability": round(model_p, 5),
                        "market_implied_prob": round(market_p, 5),
                        "estimated_payout": round(est_payout, 2),
                        "expected_value": round(ev, 3),
                        "ev_margin_pct": round(ev * 100, 1),
                    })

        # Trifecta permutations (top-5 → up to 60 combos)
        for i in range(len(top_n)):
            for j in range(len(top_n)):
                if j == i:
                    continue
                for k in range(len(top_n)):
                    if k in (i, j):
                        continue
                    model_p = self._harville_trifecta_prob_discounted(
                        model_probs[i], model_probs[j], model_probs[k]
                    )
                    market_p = self._harville_trifecta_prob(
                        market_probs[i], market_probs[j], market_probs[k]
                    )
                    if model_p <= 0 or market_p <= 0:
                        continue
                    est_payout = (1.0 / market_p) * (1.0 - tk.get("trifecta", 0.2364))
                    ev = (model_p * est_payout) - 1.0
                    if ev >= 0.18:
                        ev_plays.append({
                            "bet_type": "trifecta",
                            "horses": [names[i], names[j], names[k]],
                            "harville_probability": round(model_p, 5),
                            "market_implied_prob": round(market_p, 5),
                            "estimated_payout": round(est_payout, 2),
                            "expected_value": round(ev, 3),
                            "ev_margin_pct": round(ev * 100, 1),
                        })

        # Sort by EV descending, cap at top 10
        ev_plays.sort(key=lambda x: x['expected_value'], reverse=True)
        return ev_plays[:10]

    def _generate_betting_strategy(self, predictions: List[Dict], confidence_analysis: Dict,
                                 value_opportunities: List[Dict], risk_assessment: Dict) -> Dict:
        """Generate comprehensive betting strategy"""
        strategy = {
            "primary_plays": [],
            "value_plays": [],
            "exotic_suggestions": [],
            "bankroll_allocation": risk_assessment.get('bankroll_allocation', {}),
            "overall_approach": risk_assessment.get('recommended_approach', '')
        }
        
        # Primary plays (high confidence)
        for horse_name, confidence_data in confidence_analysis.items():
            if confidence_data['level'] in ['high', 'very_high']:
                strategy["primary_plays"].append({
                    "horse": horse_name,
                    "bet_types": ["win", "place"],
                    "confidence": confidence_data['score'],
                    "reasoning": f"High confidence ({confidence_data['level']}) based on strong algorithmic rating"
                })
        
        # Value plays
        for value_opp in value_opportunities[:2]:  # Top 2 value opportunities
            strategy["value_plays"].append({
                "horse": value_opp['horse_name'],
                "bet_types": ["win", "exacta_key"],
                "value_score": value_opp['value_score'],
                "reasoning": f"Value opportunity with {value_opp['value_type']}"
            })
        
        # Exotic suggestions (legacy fallback — kept for backward compat)
        if len(predictions) >= 4:
            top_4 = [p.get('horse_name', '') for p in predictions[:4]]
            strategy["exotic_suggestions"] = [
                {"bet_type": "exacta", "horses": top_4[:2], "cost": "low"},
                {"bet_type": "trifecta", "horses": top_4[:3], "cost": "medium"},
                {"bet_type": "superfecta", "horses": top_4, "cost": "high"}
            ]

        # ── Inject research-backed strategies ───────────────────────────
        # Strategy 1: Consecutive-ranking exotic grouping
        exotic_grouping = self._compute_exotic_grouping(predictions)
        strategy["exotic_grouping"] = exotic_grouping or {"triggered": False}

        # Strategy 2: Upset play with favourite hedge
        upset_hedge = self._compute_upset_hedge(predictions)
        strategy["upset_hedge"] = upset_hedge or {"triggered": False}

        # Strategy 3: High-odds EV exotics
        ev_exotics = self._compute_high_odds_value_exotics(predictions)
        strategy["high_odds_value_exotics"] = ev_exotics if ev_exotics else []

        # Longshot value flags (Prelec misperception correction)
        longshot_flags = self._compute_longshot_flags(predictions)
        strategy["longshot_flags"] = longshot_flags

        return strategy
    
    def _extract_track_conditions(self, race_data: Dict) -> Dict:
        """Extract and standardize track conditions"""
        conditions = race_data.get('conditions', '').lower()
        surface = race_data.get('surface', '').lower()
        
        return {
            "surface": surface,
            "condition": conditions,
            "weather_impact": "unknown",  # Would need weather data
            "bias_potential": "medium"    # Default assumption
        }
    
    def _store_analysis_patterns(self, race_data: Dict, analysis: Dict):
        """Store analysis patterns for future learning"""
        track_code = race_data.get('track_code', 'UNK')
        
        if track_code not in self.historical_patterns:
            self.historical_patterns[track_code] = []
        
        pattern_data = {
            "timestamp": time.time(),
            "race_type": race_data.get('race_type', ''),
            "distance": race_data.get('distance', ''),
            "surface": race_data.get('surface', ''),
            "field_strength": analysis.get('confidence_analysis', {}),
            "value_opportunities": len(analysis.get('value_opportunities', [])),
            "risk_level": analysis.get('risk_assessment', {}).get('overall_risk', 'moderate')
        }
        
        self.historical_patterns[track_code].append(pattern_data)
        
        # Keep only recent patterns (last 100 races per track)
        if len(self.historical_patterns[track_code]) > 100:
            self.historical_patterns[track_code] = self.historical_patterns[track_code][-100:]
    
    def get_enhancement_statistics(self) -> Dict:
        """Get statistics about analysis enhancements"""
        total_patterns = sum(len(patterns) for patterns in self.historical_patterns.values())
        
        return {
            "total_patterns_stored": total_patterns,
            "tracks_analyzed": len(self.historical_patterns),
            "track_biases_learned": len(self.track_biases),
            "jockey_trainer_insights": len(self.jockey_trainer_insights)
        }
