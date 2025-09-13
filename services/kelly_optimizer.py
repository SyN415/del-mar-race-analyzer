#!/usr/bin/env python3
"""
Kelly Criterion Optimizer for Horse Racing Bets
Implements optimal bet sizing with bankroll management and risk controls
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class KellyCriterionOptimizer:
    """
    Implements Kelly Criterion for optimal bet sizing in horse racing
    
    Features:
    - Calculates optimal stake size based on win probability and odds
    - Enforces maximum 5% bankroll allocation per bet
    - Implements 20% drawdown stop-loss protection
    - Comprehensive logging for audit and analysis
    
    Integration:
    - Designed to work with prediction engine outputs
    - Returns stake size compatible with UI display requirements
    """
    
    def __init__(self, max_allocation: float = 0.05, drawdown_threshold: float = 0.2):
        """
        Initialize Kelly Criterion optimizer with safety parameters
        
        Args:
            max_allocation: Maximum percentage of bankroll to allocate (default 5%)
            drawdown_threshold: Maximum drawdown before stopping (default 20%)
        """
        self.max_allocation = max_allocation
        self.drawdown_threshold = drawdown_threshold
        logger.info("Kelly Criterion optimizer initialized with %.0f%% max allocation and %.0f%% drawdown threshold",
                   max_allocation * 100, drawdown_threshold * 100)

    def calculate_optimal_stake(self, 
                              win_probability: float, 
                              decimal_odds: float,
                              current_bankroll: float,
                              initial_bankroll: float) -> Dict[str, float]:
        """
        Calculate optimal bet size using Kelly Criterion formula with safety constraints
        
        Formula: f* = (bp - q) / b
        where:
            b = odds - 1
            p = win probability
            q = 1 - p
            
        Args:
            win_probability: Probability of winning (0.0-1.0)
            decimal_odds: Decimal odds (e.g., 3.0 for 2/1)
            current_bankroll: Current available bankroll
            initial_bankroll: Starting bankroll amount
            
        Returns:
            Dict containing:
                - 'stake_size': Recommended bet amount
                - 'kelly_fraction': Raw Kelly fraction before constraints
                - 'confidence': Confidence in recommendation (0-100)
                - 'status': Explanation of calculation outcome
        """
        # Validate inputs
        if not (0 <= win_probability <= 1):
            logger.error("Invalid win probability: %.4f (must be 0-1)", win_probability)
            return self._create_error_response("Invalid win probability")
            
        if decimal_odds <= 1:
            logger.error("Invalid odds: %.2f (must be > 1.0)", decimal_odds)
            return self._create_error_response("Invalid odds")
            
        if current_bankroll <= 0 or initial_bankroll <= 0:
            logger.error("Invalid bankroll amounts: current=%.2f, initial=%.2f", 
                        current_bankroll, initial_bankroll)
            return self._create_error_response("Invalid bankroll amounts")

        # Calculate Kelly fraction
        b = decimal_odds - 1
        q = 1 - win_probability
        kelly_fraction = (b * win_probability - q) / b
        
        logger.debug("Kelly calculation: b=%.2f, p=%.4f, q=%.4f, f*=%.4f", 
                    b, win_probability, q, kelly_fraction)

        # Check drawdown threshold
        drawdown = 1 - (current_bankroll / initial_bankroll)
        if drawdown >= self.drawdown_threshold:
            logger.warning("Stop-loss triggered: %.1f%% drawdown (threshold=%.1f%%)", 
                          drawdown * 100, self.drawdown_threshold * 100)
            return {
                'stake_size': 0.0,
                'kelly_fraction': kelly_fraction,
                'confidence': 0.0,
                'status': f'Stop-loss at {self.drawdown_threshold*100:.0f}% drawdown'
            }

        # Apply maximum allocation constraint
        constrained_fraction = min(kelly_fraction, self.max_allocation)
        constrained_fraction = max(constrained_fraction, 0.0)  # Ensure non-negative
        
        # Calculate final stake size
        stake_size = constrained_fraction * current_bankroll
        confidence = self._calculate_confidence(win_probability, decimal_odds)
        
        logger.info("Calculated stake: $%.2f (%.1f%% of bankroll) | Kelly fraction: %.4f", 
                   stake_size, constrained_fraction * 100, kelly_fraction)
        
        return {
            'stake_size': round(stake_size, 2),
            'kelly_fraction': round(kelly_fraction, 4),
            'confidence': round(confidence, 1),
            'status': f'Valid recommendation ({constrained_fraction*100:.1f}% allocation)'
        }

    def _calculate_confidence(self, win_probability: float, decimal_odds: float) -> float:
        """Calculate confidence score for the recommendation (0-100)"""
        # Base confidence on probability-odds alignment
        implied_prob = 1 / decimal_odds
        probability_edge = win_probability - implied_prob
        
        # Higher confidence when edge is positive and substantial
        if probability_edge > 0.1:
            confidence = 90.0
        elif probability_edge > 0.05:
            confidence = 75.0
        elif probability_edge > 0:
            confidence = 60.0
        else:
            confidence = 30.0  # Negative edge
        
        # Adjust for probability certainty
        if 0.3 <= win_probability <= 0.7:
            confidence *= 0.9  # Less certain in mid-range probabilities
        
        return max(10.0, min(95.0, confidence))

    def _create_error_response(self, error_msg: str) -> Dict[str, float]:
        """Create standardized error response"""
        logger.error("Kelly calculation error: %s", error_msg)
        return {
            'stake_size': 0.0,
            'kelly_fraction': 0.0,
            'confidence': 0.0,
            'status': f'ERROR: {error_msg}'
        }

    def format_for_ui(self, 
                     calculation_result: Dict[str, float], 
                     win_probability: float) -> Dict[str, str]:
        """
        Format Kelly calculation results for UI display
        
        Args:
            calculation_result: Raw calculation output
            win_probability: Original win probability
            
        Returns:
            Dict with UI-friendly formatted values
        """
        if calculation_result.get('stake_size', 0) <= 0:
            return {
                'stake_size': '$0.00',
                'kelly_fraction': 'N/A',
                'confidence': f"{calculation_result.get('confidence', 0):.0f}%",
                'status': calculation_result.get('status', 'No bet recommended')
            }
            
        return {
            'stake_size': f"${calculation_result['stake_size']:,.2f}",
            'kelly_fraction': f"{calculation_result['kelly_fraction'] * 100:.1f}%",
            'confidence': f"{calculation_result['confidence']:.0f}%",
            'win_probability': f"{win_probability * 100:.1f}%",
            'status': calculation_result['status']
        }