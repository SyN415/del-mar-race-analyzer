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
    
    def __init__(self, openrouter_client: OpenRouterClient):
        self.ai_client = openrouter_client
        self.historical_patterns: Dict[str, List[Dict]] = {}
        self.track_biases: Dict[str, Dict] = {}
        self.jockey_trainer_insights: Dict[str, Dict] = {}
        
    async def enhance_race_analysis(self, race_data: Dict, horse_predictions: List[Dict], 
                                  historical_data: Dict = None) -> Dict:
        """
        Enhance race analysis with AI insights and confidence scoring
        
        Args:
            race_data: Race information (distance, surface, conditions, etc.)
            horse_predictions: Initial algorithmic predictions
            historical_data: Historical performance data if available
            
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
        
        # Get AI-powered enhancement
        ai_enhancement = await self.ai_client.enhance_predictions(
            race_data, 
            horse_predictions, 
            horse_predictions
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
        
        # Exotic suggestions
        if len(predictions) >= 4:
            top_4 = [p.get('horse_name', '') for p in predictions[:4]]
            strategy["exotic_suggestions"] = [
                {"bet_type": "exacta", "horses": top_4[:2], "cost": "low"},
                {"bet_type": "trifecta", "horses": top_4[:3], "cost": "medium"},
                {"bet_type": "superfecta", "horses": top_4, "cost": "high"}
            ]
        
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
