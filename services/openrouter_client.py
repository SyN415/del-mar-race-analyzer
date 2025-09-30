#!/usr/bin/env python3
"""
OpenRouter Client Service - Enhanced Version
Handles AI model communication for enhanced analysis and scraping assistance
with improved error handling, model management, and API optimization
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from enum import Enum

import aiohttp
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class ModelTier(Enum):
    """Model performance tiers for intelligent selection"""
    FAST = "fast"      # Quick responses, lower cost
    BALANCED = "balanced"  # Good balance of speed and quality
    PREMIUM = "premium"    # Highest quality, slower/more expensive

@dataclass
class ModelConfig:
    """Configuration for AI models"""
    name: str
    tier: ModelTier
    max_tokens: int
    cost_per_1k_tokens: float
    avg_response_time: float
    reliability_score: float

class APIUsageTracker:
    """Track API usage and costs"""
    def __init__(self):
        self.total_requests = 0
        self.total_tokens = 0
        self.total_cost = 0.0
        self.error_count = 0
        self.response_times = []

    def record_request(self, tokens: int, cost: float, response_time: float, success: bool):
        self.total_requests += 1
        if success:
            self.total_tokens += tokens
            self.total_cost += cost
            self.response_times.append(response_time)
        else:
            self.error_count += 1

    def get_stats(self) -> Dict:
        avg_response_time = sum(self.response_times) / len(self.response_times) if self.response_times else 0
        success_rate = (self.total_requests - self.error_count) / self.total_requests if self.total_requests > 0 else 0

        return {
            "total_requests": self.total_requests,
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "error_count": self.error_count,
            "success_rate": success_rate,
            "avg_response_time": avg_response_time
        }

class OpenRouterClient:
    """Enhanced client for OpenRouter AI API integration"""

    # Available models with configurations
    MODELS = {
        # Fast tier - Quick responses for simple tasks
        "x-ai/grok-code-fast-1": ModelConfig("x-ai/grok-code-fast-1", ModelTier.FAST, 8192, 0.003, 2.0, 0.94),

        # Balanced tier - Good performance for most tasks
        "z-ai/glm-4.5": ModelConfig("z-ai/glm-4.5", ModelTier.BALANCED, 8192, 0.02, 3.5, 0.96),
        "anthropic/claude-3.5-haiku": ModelConfig("anthropic/claude-3.5-haiku", ModelTier.BALANCED, 8192, 0.001, 2.5, 0.97),

        # Premium tier - Best quality for complex analysis
        "anthropic/claude-sonnet-4.5": ModelConfig("anthropic/claude-sonnet-4.5", ModelTier.PREMIUM, 200000, 0.003, 3.5, 0.99),
        "moonshotai/kimi-k2-0905": ModelConfig("moonshotai/kimi-k2-0905", ModelTier.PREMIUM, 16384, 0.04, 4.0, 0.98),
        "qwen/qwen3-coder": ModelConfig("qwen/qwen3-coder", ModelTier.PREMIUM, 12288, 0.035, 3.8, 0.97),
    }

    def __init__(self, config):
        self.config = config
        self.api_key = getattr(config, 'openrouter_api_key', None) or self._get_api_key_from_env()
        self.base_url = "https://openrouter.ai/api/v1"
        self.session = None
        self.usage_tracker = APIUsageTracker()
        self.retry_config = {
            "max_retries": 3,
            "base_delay": 1.0,
            "max_delay": 30.0,
            "backoff_factor": 2.0
        }

        # Model selection preferences - Claude Sonnet 4.5 as primary
        self.preferred_models = {
            "scraping": "anthropic/claude-sonnet-4.5",  # Best reasoning for scraping strategies
            "analysis": "anthropic/claude-sonnet-4.5",  # Excellent for complex analysis
            "betting": "anthropic/claude-sonnet-4.5",  # Premium reasoning for betting recommendations
            "general": "anthropic/claude-sonnet-4.5",  # Default for all tasks
            "fallback": "anthropic/claude-3.5-haiku"  # Fast Claude fallback
        }
        
    def _get_api_key_from_env(self) -> Optional[str]:
        """Get API key from environment variables"""
        import os
        return os.getenv('OPENROUTER_API_KEY')
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    def get_optimal_model(self, task_type: str = "general", tier: ModelTier = None) -> str:
        """Select optimal model based on task type and requirements"""
        if tier:
            # Filter models by tier
            tier_models = [name for name, config in self.MODELS.items() if config.tier == tier]
            if tier_models:
                return max(tier_models, key=lambda m: self.MODELS[m].reliability_score)

        # Use task-specific preferences
        preferred = self.preferred_models.get(task_type, "anthropic/claude-sonnet-4.5")
        return preferred if preferred in self.MODELS else "anthropic/claude-sonnet-4.5"

    async def call_model(self, model: str = None, prompt: str = "", context: Dict = None,
                        max_tokens: int = None, temperature: float = 0.7,
                        task_type: str = "general", tier: ModelTier = None) -> str:
        """
        Enhanced API call to OpenRouter model with intelligent model selection

        Args:
            model: Specific model identifier (optional, will auto-select if None)
            prompt: The prompt to send to the model
            context: Additional context data
            max_tokens: Maximum tokens in response (uses model default if None)
            temperature: Sampling temperature
            task_type: Type of task for optimal model selection
            tier: Preferred model tier

        Returns:
            Model response text
        """
        if not self.api_key:
            logger.warning("OpenRouter API key not configured, returning fallback response")
            return self._generate_fallback_response(prompt, context, task_type)

        # Auto-select model if not specified
        if not model:
            model = self.get_optimal_model(task_type, tier)

        # Use model-specific defaults
        model_config = self.MODELS.get(model)
        if model_config and max_tokens is None:
            max_tokens = min(1000, model_config.max_tokens // 2)  # Conservative default
        elif max_tokens is None:
            max_tokens = 1000
        
        # Implement retry logic with exponential backoff
        for attempt in range(self.retry_config["max_retries"] + 1):
            try:
                start_time = time.time()

                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://del-mar-analyzer.local",
                    "X-Title": "Del Mar Race Analyzer"
                }

                # Enhanced system prompt based on task type
                system_prompts = {
                    "scraping": "You are an expert web scraping specialist with deep knowledge of HTML parsing, CSS selectors, and anti-bot countermeasures.",
                    "analysis": "You are an expert horse racing analyst with deep knowledge of handicapping, track conditions, and performance analysis.",
                    "betting": "You are an expert horse racing handicapper specializing in betting strategies, risk management, and value identification.",
                    "general": "You are an expert horse racing analyst with deep knowledge of handicapping, track conditions, and betting strategies."
                }

                # Prepare the request payload
                payload = {
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": system_prompts.get(task_type, system_prompts["general"])
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }

                # Add context if provided
                if context:
                    context_str = json.dumps(context, indent=2)
                    payload["messages"][0]["content"] += f"\n\nContext data:\n{context_str}"

                if not self.session:
                    self.session = aiohttp.ClientSession()

                # Calculate timeout based on model performance
                timeout_seconds = 30
                if model_config:
                    timeout_seconds = max(30, int(model_config.avg_response_time * 3))

                async with self.session.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout_seconds)
                ) as response:

                    response_time = time.time() - start_time

                    if response.status == 200:
                        result = await response.json()
                        response_text = result["choices"][0]["message"]["content"]

                        # Track successful request
                        estimated_tokens = len(response_text.split()) * 1.3  # Rough estimate
                        estimated_cost = (estimated_tokens / 1000) * (model_config.cost_per_1k_tokens if model_config else 0.02)
                        self.usage_tracker.record_request(int(estimated_tokens), estimated_cost, response_time, True)

                        logger.info(f"OpenRouter API call successful: {model} in {response_time:.2f}s")
                        return response_text

                    elif response.status == 429:  # Rate limit
                        if attempt < self.retry_config["max_retries"]:
                            delay = min(
                                self.retry_config["base_delay"] * (self.retry_config["backoff_factor"] ** attempt),
                                self.retry_config["max_delay"]
                            )
                            logger.warning(f"Rate limited, retrying in {delay:.1f}s (attempt {attempt + 1})")
                            await asyncio.sleep(delay)
                            continue

                    else:
                        error_text = await response.text()
                        logger.error(f"OpenRouter API error {response.status}: {error_text}")

                        # Track failed request
                        self.usage_tracker.record_request(0, 0, response_time, False)

                        if attempt < self.retry_config["max_retries"] and response.status >= 500:
                            # Retry on server errors
                            delay = self.retry_config["base_delay"] * (self.retry_config["backoff_factor"] ** attempt)
                            logger.warning(f"Server error, retrying in {delay:.1f}s (attempt {attempt + 1})")
                            await asyncio.sleep(delay)
                            continue

                        return self._generate_fallback_response(prompt, context, task_type)

            except asyncio.TimeoutError:
                logger.error(f"OpenRouter API timeout on attempt {attempt + 1}")
                if attempt < self.retry_config["max_retries"]:
                    delay = self.retry_config["base_delay"] * (self.retry_config["backoff_factor"] ** attempt)
                    await asyncio.sleep(delay)
                    continue
                self.usage_tracker.record_request(0, 0, 0, False)
                return self._generate_fallback_response(prompt, context, task_type)

            except Exception as e:
                logger.error(f"OpenRouter API call failed on attempt {attempt + 1}: {e}")
                if attempt < self.retry_config["max_retries"]:
                    delay = self.retry_config["base_delay"] * (self.retry_config["backoff_factor"] ** attempt)
                    await asyncio.sleep(delay)
                    continue
                self.usage_tracker.record_request(0, 0, 0, False)
                return self._generate_fallback_response(prompt, context, task_type)

        # All retries exhausted
        return self._generate_fallback_response(prompt, context, task_type)
    
    def _generate_fallback_response(self, prompt: str, context: Dict = None, task_type: str = "general") -> str:
        """Generate intelligent fallback response when API is unavailable"""
        fallback_responses = {
            "scraping": """
            Fallback scraping strategy:
            1. Increase delay between requests to 5-8 seconds
            2. Rotate user agents and viewport sizes
            3. Clear cookies and restart browser session
            4. Try alternative URL patterns or endpoints
            5. Implement exponential backoff on failures
            6. Check for CAPTCHA or rate limiting indicators
            7. Consider using different browser profiles
            """,
            "analysis": """
            AI analysis enhancement (fallback mode):
            The traditional algorithmic analysis provides solid baseline predictions.
            Key factors to emphasize:
            - Recent speed figures and consistency trends
            - Jockey/trainer performance at this specific track
            - Post position advantages for this distance/surface
            - Track condition preferences and bias patterns
            - Class level changes and equipment modifications
            - Recent workout patterns and timing
            """,
            "betting": """
            Betting strategy (fallback mode):
            Conservative approach recommended when AI unavailable:
            - Focus on highest-confidence algorithmic picks
            - Limit exotic betting to strong overlays
            - Use smaller bet sizes to manage risk
            - Prioritize Win/Place bets over complex exotics
            - Look for value in Place/Show pools on favorites
            """,
            "general": "AI assistant temporarily unavailable. Using algorithmic analysis with conservative recommendations."
        }

        return fallback_responses.get(task_type, fallback_responses["general"])

    def get_usage_stats(self) -> Dict:
        """Get API usage statistics"""
        return self.usage_tracker.get_stats()

    def reset_usage_stats(self):
        """Reset usage tracking"""
        self.usage_tracker = APIUsageTracker()
    
    async def analyze_page_layout(self, html_content: str) -> Dict:
        """AI analyzes page structure to identify data extraction strategies"""
        prompt = f"""
        Analyze this HTML content and suggest the best data extraction strategy:

        HTML snippet (first 2000 chars):
        {html_content[:2000]}

        Please identify:
        1. Main data tables and their structure
        2. Key CSS selectors for horse names, odds, and performance data
        3. Any dynamic content loading patterns (JavaScript, AJAX)
        4. Potential anti-scraping measures (rate limiting, CAPTCHAs)
        5. Recommended extraction approach with fallback strategies

        Respond in JSON format with specific selectors and strategies.
        Example format:
        {{
            "main_selectors": {{"horse_name": ".horse-name", "odds": ".odds"}},
            "fallback_selectors": {{"horse_name": "td:nth-child(2)", "odds": "td:last-child"}},
            "dynamic_content": true/false,
            "anti_scraping_detected": ["rate_limiting", "captcha"],
            "recommended_strategy": "detailed approach"
        }}
        """

        try:
            response = await self.call_model(
                task_type="scraping",
                prompt=prompt,
                max_tokens=800,
                temperature=0.3  # Lower temperature for more consistent JSON
            )

            # Try to parse as JSON, fallback to text analysis
            try:
                return json.loads(response)
            except json.JSONDecodeError:
                # Try to extract JSON from response if it's wrapped in text
                import re
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    try:
                        return json.loads(json_match.group())
                    except:
                        pass
                return {"analysis": response, "format": "text", "json_parse_failed": True}

        except Exception as e:
            logger.error(f"Page layout analysis failed: {e}")
            return {"error": str(e), "fallback_strategy": "Use basic CSS selectors and increase delays"}
    
    async def suggest_scraping_strategy(self, error_message: str, page_content: str = "",
                                      url: str = "", previous_attempts: List[str] = None) -> Dict:
        """AI suggests alternative approaches when scraping fails"""
        previous_attempts = previous_attempts or []

        prompt = f"""
        A web scraping operation failed with this error: {error_message}

        URL: {url}
        Page content sample: {page_content[:1000] if page_content else "Not available"}
        Previous failed attempts: {', '.join(previous_attempts) if previous_attempts else "None"}

        Please suggest specific strategies to overcome this issue:
        1. Technical adjustments (delays, headers, user agents, etc.)
        2. Alternative selectors or approaches
        3. Fallback data sources or endpoints
        4. Error recovery mechanisms
        5. Detection and handling of anti-bot measures

        Provide a prioritized list of solutions, avoiding previously failed approaches.
        Format as JSON with strategy priority and implementation details.
        """

        try:
            response = await self.call_model(
                task_type="scraping",
                prompt=prompt,
                max_tokens=600,
                temperature=0.4
            )

            # Try to parse as structured response
            try:
                return json.loads(response)
            except:
                return {
                    "strategies": response,
                    "format": "text",
                    "priority": "high" if "captcha" in error_message.lower() or "blocked" in error_message.lower() else "medium"
                }

        except Exception as e:
            logger.error(f"Scraping strategy suggestion failed: {e}")
            return {
                "error": str(e),
                "fallback_strategies": [
                    "Increase delay to 8-12 seconds",
                    "Rotate user agents",
                    "Clear browser cache and cookies",
                    "Try different browser profile",
                    "Use alternative URL endpoints"
                ]
            }
    
    async def enhance_predictions(self, race_data: Dict, horse_data: List[Dict],
                                initial_predictions: List[Dict]) -> Dict:
        """AI refines predictions with contextual analysis and confidence scoring"""

        # Prepare comprehensive race context
        race_context = {
            "race_info": {
                "type": race_data.get('race_type', 'Unknown'),
                "distance": race_data.get('distance', 'Unknown'),
                "surface": race_data.get('surface', 'Unknown'),
                "conditions": race_data.get('conditions', 'Unknown'),
                "purse": race_data.get('purse', 'Unknown'),
                "field_size": len(horse_data) if horse_data else len(initial_predictions)
            },
            "top_predictions": initial_predictions[:5],  # Include top 5 for better analysis
            "field_strength": self._assess_field_strength(initial_predictions)
        }

        prompt = f"""
        Analyze this horse race and provide enhanced predictions with confidence scoring:

        Race Context:
        {json.dumps(race_context, indent=2)}

        Please provide detailed analysis including:
        1. Confidence score (1-10) for each top 3 picks with reasoning
        2. Key factors that could change the predicted outcome
        3. Risk/reward analysis for different bet types
        4. Value opportunities in the field
        5. Alternative scenarios (pace, track bias, weather impact)
        6. Recommended betting strategy with bankroll allocation

        Format response as JSON with structured confidence scores and insights.
        """

        try:
            response = await self.call_model(
                task_type="analysis",
                prompt=prompt,
                context=race_context,
                max_tokens=1000,
                temperature=0.6
            )

            # Try to parse structured response
            try:
                ai_analysis = json.loads(response)
                return {
                    "ai_insights": ai_analysis,
                    "enhanced_predictions": self._merge_ai_insights(initial_predictions, ai_analysis),
                    "confidence_boost": True,
                    "analysis_quality": "structured"
                }
            except:
                return {
                    "ai_insights": response,
                    "enhanced_predictions": initial_predictions,
                    "confidence_boost": True,
                    "analysis_quality": "text"
                }

        except Exception as e:
            logger.error(f"Prediction enhancement failed: {e}")
            return {
                "ai_insights": "AI enhancement unavailable - using algorithmic analysis only",
                "enhanced_predictions": initial_predictions,
                "confidence_boost": False,
                "error": str(e)
            }

    def _assess_field_strength(self, predictions: List[Dict]) -> str:
        """Assess overall field strength based on prediction spread"""
        if not predictions or len(predictions) < 3:
            return "insufficient_data"

        top_rating = predictions[0].get('composite_rating', 0)
        third_rating = predictions[2].get('composite_rating', 0) if len(predictions) > 2 else 0

        rating_spread = top_rating - third_rating

        if rating_spread > 15:
            return "strong_favorite"
        elif rating_spread > 8:
            return "moderate_favorite"
        else:
            return "competitive_field"

    def _merge_ai_insights(self, predictions: List[Dict], ai_analysis: Dict) -> List[Dict]:
        """Merge AI insights with algorithmic predictions"""
        enhanced_predictions = predictions.copy()

        # Add AI confidence scores if available
        if isinstance(ai_analysis, dict) and "confidence_scores" in ai_analysis:
            confidence_scores = ai_analysis["confidence_scores"]
            for i, pred in enumerate(enhanced_predictions[:len(confidence_scores)]):
                pred["ai_confidence"] = confidence_scores[i]
                pred["enhanced"] = True

        return enhanced_predictions
    
    async def generate_betting_recommendations(self, race_analyses: List[Dict],
                                         bankroll: float = 1000.0) -> Dict:
        """Generate strategic betting recommendations across all races with bankroll management"""

        # Prepare comprehensive betting context
        betting_context = {
            "total_races": len(race_analyses),
            "bankroll": bankroll,
            "race_summaries": [],
            "high_confidence_plays": [],
            "value_opportunities": []
        }

        # Analyze each race for betting opportunities
        for race in race_analyses[:8]:  # Limit to 8 races for context size
            race_summary = {
                "race_number": race.get('race_number'),
                "field_size": len(race.get('predictions', [])),
                "top_pick": {
                    "horse": race.get('predictions', [{}])[0].get('horse_name') if race.get('predictions') else None,
                    "win_prob": race.get('predictions', [{}])[0].get('win_probability') if race.get('predictions') else None,
                    "composite_rating": race.get('predictions', [{}])[0].get('composite_rating') if race.get('predictions') else None
                },
                "field_strength": self._assess_field_strength(race.get('predictions', []))
            }
            betting_context["race_summaries"].append(race_summary)

            # Identify high confidence and value plays
            if race.get('predictions'):
                top_pick = race['predictions'][0]
                if top_pick.get('win_probability', 0) > 35:
                    betting_context["high_confidence_plays"].append({
                        "race": race.get('race_number'),
                        "horse": top_pick.get('horse_name'),
                        "confidence": top_pick.get('win_probability')
                    })

                # Look for value in lower-rated horses with decent probability
                for pred in race['predictions'][1:4]:
                    if pred.get('win_probability', 0) > 15 and pred.get('composite_rating', 0) > 70:
                        betting_context["value_opportunities"].append({
                            "race": race.get('race_number'),
                            "horse": pred.get('horse_name'),
                            "value_score": pred.get('win_probability', 0) / max(pred.get('composite_rating', 1), 1)
                        })

        prompt = f"""
        Create a comprehensive betting strategy for this race card:

        Betting Context:
        {json.dumps(betting_context, indent=2)}

        Provide detailed recommendations including:
        1. Single race bets (Win/Place/Show) with specific amounts
        2. Multi-race exotic opportunities (Daily Double, Pick 3, Pick 4)
        3. Risk management strategy (percentage of bankroll per bet type)
        4. Bankroll allocation across the card
        5. Value betting opportunities and overlay situations
        6. Contingency plans if early races don't go as expected

        Format as JSON with specific bet amounts and reasoning.
        Target total risk: 15-25% of bankroll with potential 3-5x return.
        """

        try:
            response = await self.call_model(
                task_type="betting",
                prompt=prompt,
                context=betting_context,
                max_tokens=1200,
                temperature=0.5
            )

            # Try to parse structured response
            try:
                betting_strategy = json.loads(response)
                return {
                    "betting_strategy": betting_strategy,
                    "context": betting_context,
                    "generated_at": time.time(),
                    "format": "structured"
                }
            except:
                return {
                    "betting_strategy": response,
                    "context": betting_context,
                    "generated_at": time.time(),
                    "format": "text"
                }

        except Exception as e:
            logger.error(f"Betting recommendation generation failed: {e}")
            return {
                "error": str(e),
                "fallback_strategy": self._generate_conservative_betting_strategy(betting_context)
            }

    def _generate_conservative_betting_strategy(self, context: Dict) -> Dict:
        """Generate conservative betting strategy when AI is unavailable"""
        high_confidence = context.get("high_confidence_plays", [])
        bankroll = context.get("bankroll", 1000)

        strategy = {
            "approach": "conservative",
            "total_risk": bankroll * 0.15,  # 15% of bankroll
            "single_race_bets": [],
            "exotic_bets": []
        }

        # Recommend Win bets on high confidence plays
        bet_amount = (bankroll * 0.10) / max(len(high_confidence), 1)
        for play in high_confidence[:3]:  # Limit to top 3
            strategy["single_race_bets"].append({
                "race": play["race"],
                "horse": play["horse"],
                "bet_type": "Win",
                "amount": min(bet_amount, 50),  # Cap individual bets
                "reasoning": f"High confidence ({play['confidence']:.1f}%)"
            })

        return strategy
    
    async def health_check(self) -> Dict:
        """Comprehensive health check of OpenRouter API and models"""
        if not self.api_key:
            return {
                "status": "unavailable",
                "reason": "No API key configured",
                "models_available": 0,
                "usage_stats": self.get_usage_stats()
            }

        health_results = {
            "status": "unknown",
            "models_tested": 0,
            "models_healthy": 0,
            "response_times": {},
            "usage_stats": self.get_usage_stats(),
            "timestamp": time.time()
        }

        # Test different model tiers
        test_models = [
            ("x-ai/grok-code-fast-1", "fast"),
            ("anthropic/claude-3.5-haiku", "balanced"),
            ("anthropic/claude-sonnet-4.5", "premium")
        ]

        for model, tier in test_models:
            try:
                start_time = time.time()
                response = await self.call_model(
                    model=model,
                    prompt="Respond with 'HEALTHY' if you can process this request.",
                    max_tokens=10,
                    temperature=0.1
                )
                response_time = time.time() - start_time

                health_results["models_tested"] += 1
                health_results["response_times"][model] = response_time

                if "HEALTHY" in response.upper() or len(response.strip()) > 0:
                    health_results["models_healthy"] += 1

            except Exception as e:
                logger.warning(f"Health check failed for {model}: {e}")
                health_results["response_times"][model] = -1

        # Determine overall status
        if health_results["models_healthy"] == 0:
            health_results["status"] = "error"
        elif health_results["models_healthy"] == health_results["models_tested"]:
            health_results["status"] = "healthy"
        else:
            health_results["status"] = "degraded"

        return health_results

    async def get_available_models(self) -> List[Dict]:
        """Get list of available models with their configurations"""
        return [
            {
                "name": name,
                "tier": config.tier.value,
                "max_tokens": config.max_tokens,
                "cost_per_1k": config.cost_per_1k_tokens,
                "avg_response_time": config.avg_response_time,
                "reliability": config.reliability_score
            }
            for name, config in self.MODELS.items()
        ]

    async def estimate_cost(self, prompt: str, model: str = None, max_tokens: int = 1000) -> Dict:
        """Estimate cost for a given prompt and model"""
        if not model:
            model = self.get_optimal_model()

        model_config = self.MODELS.get(model)
        if not model_config:
            return {"error": "Unknown model"}

        # Rough token estimation (words * 1.3)
        estimated_input_tokens = len(prompt.split()) * 1.3
        estimated_total_tokens = estimated_input_tokens + max_tokens

        estimated_cost = (estimated_total_tokens / 1000) * model_config.cost_per_1k_tokens

        return {
            "model": model,
            "estimated_input_tokens": int(estimated_input_tokens),
            "max_output_tokens": max_tokens,
            "estimated_total_tokens": int(estimated_total_tokens),
            "estimated_cost": round(estimated_cost, 4),
            "currency": "USD"
        }

    async def generate_betting_recommendations(self, race_analyses: List[Dict], bankroll: float = 1000.0) -> Dict:
        """
        Generate comprehensive betting recommendations across all races

        Args:
            race_analyses: List of race analysis results
            bankroll: Available bankroll for betting

        Returns:
            Comprehensive betting strategy
        """
        try:
            # Prepare analysis context
            context = {
                "total_races": len(race_analyses),
                "bankroll": bankroll,
                "race_summaries": []
            }

            # Extract key information from each race
            for race in race_analyses:
                if race.get('predictions'):
                    top_picks = race['predictions'][:3]
                    race_summary = {
                        "race_number": race.get('race_number'),
                        "top_picks": [
                            {
                                "horse": pick.get('horse_name'),
                                "rating": pick.get('composite_rating'),
                                "probability": pick.get('win_probability')
                            }
                            for pick in top_picks
                        ]
                    }

                    # Add AI enhancement data if available
                    if race.get('ai_enhancement'):
                        race_summary["ai_insights"] = {
                            "confidence": race['ai_enhancement'].get('overall_confidence'),
                            "value_opportunities": race['ai_enhancement'].get('value_opportunities', [])
                        }

                    context["race_summaries"].append(race_summary)

            # Generate AI betting strategy
            prompt = f"""
            Analyze this complete race card and generate a comprehensive betting strategy:

            Race Card Summary:
            - Total Races: {context['total_races']}
            - Available Bankroll: ${bankroll}
            - Race Details: {context['race_summaries'][:5]}  # Limit context size

            Provide a strategic betting plan including:
            1. Primary plays (high confidence bets)
            2. Value opportunities (overlay situations)
            3. Exotic betting suggestions (exactas, trifectas, etc.)
            4. Bankroll allocation recommendations
            5. Risk management strategy

            Format as JSON with specific bet recommendations and reasoning.
            """

            response = await self.call_model(
                task_type="betting",
                prompt=prompt,
                max_tokens=800,
                temperature=0.3
            )

            # Try to parse as JSON, fallback to text
            try:
                betting_strategy = json.loads(response)
            except:
                betting_strategy = {
                    "strategy_text": response,
                    "primary_plays": [],
                    "value_plays": [],
                    "exotic_suggestions": []
                }

            return {
                "betting_strategy": betting_strategy,
                "bankroll": bankroll,
                "generated_at": datetime.now().isoformat(),
                "model_used": self.get_optimal_model("betting")
            }

        except Exception as e:
            logger.error(f"Failed to generate betting recommendations: {e}")
            return {
                "error": str(e),
                "betting_strategy": "Unable to generate AI betting recommendations at this time."
            }

    def get_statistics(self) -> Dict:
        """Get comprehensive usage statistics"""
        total_requests = sum(self.usage_stats.values())

        return {
            "total_requests": total_requests,
            "requests_by_model": dict(self.usage_stats),
            "total_cost": self.total_cost,
            "average_response_time": sum(self.response_times) / len(self.response_times) if self.response_times else 0,
            "health_scores": dict(self.model_health),
            "preferred_models": self.preferred_models,
            "last_request": self.last_request_time.isoformat() if self.last_request_time else None
        }
