#!/usr/bin/env python3
"""
AI Scraping Assistant Service
Provides AI-guided scraping workflows with intelligent error recovery,
adaptive strategies, and anti-detection capabilities
"""

import asyncio
import json
import logging
import re
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

from services.openrouter_client import OpenRouterClient

logger = logging.getLogger(__name__)

class ScrapingDifficulty(Enum):
    """Difficulty levels for scraping operations"""
    EASY = "easy"           # Simple static content
    MODERATE = "moderate"   # Some JavaScript, basic protection
    HARD = "hard"          # Heavy JavaScript, rate limiting
    EXTREME = "extreme"    # CAPTCHA, advanced anti-bot measures

@dataclass
class ScrapingAttempt:
    """Record of a scraping attempt"""
    timestamp: float
    strategy: str
    success: bool
    error_message: str = ""
    response_time: float = 0.0
    data_extracted: bool = False

class AIScrapingAssistant:
    """AI-powered scraping assistant with adaptive strategies"""
    
    def __init__(self, openrouter_client: OpenRouterClient):
        self.ai_client = openrouter_client
        self.attempt_history: Dict[str, List[ScrapingAttempt]] = {}
        self.learned_patterns: Dict[str, Dict] = {}
        self.success_strategies: Dict[str, List[str]] = {}
        
    async def analyze_page_structure(self, html_content: str, url: str = "") -> Dict:
        """
        Analyze page structure and recommend scraping strategy
        
        Args:
            html_content: Raw HTML content
            url: Page URL for context
            
        Returns:
            Analysis results with recommended strategies
        """
        # Basic pattern detection
        basic_analysis = self._detect_basic_patterns(html_content)
        
        # Get AI-powered analysis
        ai_analysis = await self.ai_client.analyze_page_layout(html_content)
        
        # Combine analyses
        combined_analysis = {
            "url": url,
            "timestamp": time.time(),
            "basic_patterns": basic_analysis,
            "ai_analysis": ai_analysis,
            "difficulty": self._assess_difficulty(html_content, basic_analysis),
            "recommended_strategies": self._generate_strategy_recommendations(basic_analysis, ai_analysis)
        }
        
        # Store learned patterns
        domain = self._extract_domain(url)
        if domain:
            self.learned_patterns[domain] = combined_analysis
            
        return combined_analysis
    
    def _detect_basic_patterns(self, html_content: str) -> Dict:
        """Detect basic patterns in HTML content"""
        patterns = {
            "has_tables": bool(re.search(r'<table[^>]*>', html_content, re.IGNORECASE)),
            "has_javascript": bool(re.search(r'<script[^>]*>', html_content, re.IGNORECASE)),
            "has_ajax": bool(re.search(r'ajax|xhr|fetch', html_content, re.IGNORECASE)),
            "has_react": bool(re.search(r'react|redux|jsx', html_content, re.IGNORECASE)),
            "has_angular": bool(re.search(r'angular|ng-', html_content, re.IGNORECASE)),
            "has_vue": bool(re.search(r'vue\.js|v-', html_content, re.IGNORECASE)),
            "has_captcha": bool(re.search(r'captcha|recaptcha|hcaptcha', html_content, re.IGNORECASE)),
            "has_cloudflare": bool(re.search(r'cloudflare|cf-ray', html_content, re.IGNORECASE)),
            "has_rate_limiting": bool(re.search(r'rate.?limit|too.?many.?requests', html_content, re.IGNORECASE)),
            "data_in_json": bool(re.search(r'<script[^>]*type=["\']application/json["\'][^>]*>', html_content, re.IGNORECASE)),
            "lazy_loading": bool(re.search(r'lazy|data-src|loading=["\']lazy["\']', html_content, re.IGNORECASE))
        }
        
        # Count potential data elements
        patterns["table_count"] = len(re.findall(r'<table[^>]*>', html_content, re.IGNORECASE))
        patterns["form_count"] = len(re.findall(r'<form[^>]*>', html_content, re.IGNORECASE))
        patterns["div_count"] = len(re.findall(r'<div[^>]*>', html_content, re.IGNORECASE))
        
        return patterns
    
    def _assess_difficulty(self, html_content: str, basic_patterns: Dict) -> ScrapingDifficulty:
        """Assess scraping difficulty based on page characteristics"""
        difficulty_score = 0
        
        # Add points for complexity factors
        if basic_patterns.get("has_javascript"): difficulty_score += 1
        if basic_patterns.get("has_ajax"): difficulty_score += 2
        if basic_patterns.get("has_react") or basic_patterns.get("has_angular") or basic_patterns.get("has_vue"): difficulty_score += 3
        if basic_patterns.get("has_captcha"): difficulty_score += 4
        if basic_patterns.get("has_cloudflare"): difficulty_score += 2
        if basic_patterns.get("has_rate_limiting"): difficulty_score += 3
        if basic_patterns.get("lazy_loading"): difficulty_score += 2
        
        # Assess based on score
        if difficulty_score >= 8:
            return ScrapingDifficulty.EXTREME
        elif difficulty_score >= 5:
            return ScrapingDifficulty.HARD
        elif difficulty_score >= 2:
            return ScrapingDifficulty.MODERATE
        else:
            return ScrapingDifficulty.EASY
    
    def _generate_strategy_recommendations(self, basic_patterns: Dict, ai_analysis: Dict) -> List[Dict]:
        """Generate prioritized scraping strategy recommendations"""
        strategies = []
        
        # Strategy 1: Direct HTML parsing (if simple)
        if not basic_patterns.get("has_javascript") and basic_patterns.get("has_tables"):
            strategies.append({
                "name": "direct_html_parsing",
                "priority": 1,
                "description": "Parse static HTML content directly",
                "implementation": {
                    "method": "beautifulsoup",
                    "wait_time": 2,
                    "selectors": ai_analysis.get("main_selectors", {}) if isinstance(ai_analysis, dict) else {}
                }
            })
        
        # Strategy 2: JavaScript rendering (if dynamic)
        if basic_patterns.get("has_javascript") or basic_patterns.get("has_ajax"):
            strategies.append({
                "name": "javascript_rendering",
                "priority": 2,
                "description": "Render JavaScript content before parsing",
                "implementation": {
                    "method": "playwright",
                    "wait_time": 5,
                    "wait_for_selector": "table, .race-data, .horse-data",
                    "scroll_to_load": basic_patterns.get("lazy_loading", False)
                }
            })
        
        # Strategy 3: Stealth mode (if anti-bot detected)
        if basic_patterns.get("has_cloudflare") or basic_patterns.get("has_captcha"):
            strategies.append({
                "name": "stealth_mode",
                "priority": 3,
                "description": "Use stealth techniques to avoid detection",
                "implementation": {
                    "method": "playwright_stealth",
                    "wait_time": 8,
                    "user_agent_rotation": True,
                    "viewport_randomization": True,
                    "request_interception": True
                }
            })
        
        # Strategy 4: API endpoint discovery
        if basic_patterns.get("has_ajax") or basic_patterns.get("data_in_json"):
            strategies.append({
                "name": "api_endpoint_discovery",
                "priority": 4,
                "description": "Find and use API endpoints directly",
                "implementation": {
                    "method": "network_monitoring",
                    "monitor_xhr": True,
                    "extract_api_calls": True
                }
            })
        
        return sorted(strategies, key=lambda x: x["priority"])
    
    async def handle_scraping_failure(self, error_message: str, url: str, 
                                    page_content: str = "", previous_attempts: List[str] = None) -> Dict:
        """
        Handle scraping failures with AI-powered recovery strategies
        
        Args:
            error_message: The error that occurred
            url: URL that failed
            page_content: Page content if available
            previous_attempts: List of previously tried strategies
            
        Returns:
            Recovery strategy recommendations
        """
        domain = self._extract_domain(url)
        previous_attempts = previous_attempts or []
        
        # Record the failure
        if domain not in self.attempt_history:
            self.attempt_history[domain] = []
        
        self.attempt_history[domain].append(ScrapingAttempt(
            timestamp=time.time(),
            strategy="unknown",
            success=False,
            error_message=error_message
        ))
        
        # Get AI-powered suggestions
        ai_suggestions = await self.ai_client.suggest_scraping_strategy(
            error_message, page_content, url, previous_attempts
        )
        
        # Combine with learned patterns
        recovery_strategy = {
            "error_analysis": self._analyze_error_type(error_message),
            "ai_suggestions": ai_suggestions,
            "learned_strategies": self._get_learned_strategies(domain),
            "recommended_actions": self._prioritize_recovery_actions(error_message, ai_suggestions, previous_attempts)
        }
        
        return recovery_strategy
    
    def _analyze_error_type(self, error_message: str) -> Dict:
        """Analyze error type and categorize"""
        error_lower = error_message.lower()
        
        error_types = {
            "timeout": any(word in error_lower for word in ["timeout", "timed out", "connection timeout"]),
            "blocked": any(word in error_lower for word in ["blocked", "forbidden", "403", "access denied"]),
            "rate_limited": any(word in error_lower for word in ["rate limit", "too many requests", "429"]),
            "captcha": any(word in error_lower for word in ["captcha", "recaptcha", "hcaptcha"]),
            "not_found": any(word in error_lower for word in ["not found", "404", "page not found"]),
            "server_error": any(word in error_lower for word in ["500", "502", "503", "server error"]),
            "network": any(word in error_lower for word in ["network", "connection", "dns", "resolve"]),
            "parsing": any(word in error_lower for word in ["parse", "selector", "element not found"])
        }
        
        return {
            "primary_type": next((k for k, v in error_types.items() if v), "unknown"),
            "all_types": [k for k, v in error_types.items() if v],
            "severity": self._assess_error_severity(error_types)
        }
    
    def _assess_error_severity(self, error_types: Dict) -> str:
        """Assess error severity"""
        if error_types.get("captcha") or error_types.get("blocked"):
            return "high"
        elif error_types.get("rate_limited") or error_types.get("server_error"):
            return "medium"
        else:
            return "low"
    
    def _prioritize_recovery_actions(self, error_message: str, ai_suggestions: Dict, 
                                   previous_attempts: List[str]) -> List[Dict]:
        """Prioritize recovery actions based on error type and history"""
        actions = []
        error_analysis = self._analyze_error_type(error_message)
        
        # High priority actions based on error type
        if error_analysis["primary_type"] == "timeout":
            actions.append({
                "action": "increase_timeout",
                "priority": 1,
                "description": "Increase request timeout to 60 seconds",
                "implementation": {"timeout": 60, "wait_after_load": 10}
            })
        
        if error_analysis["primary_type"] == "rate_limited":
            actions.append({
                "action": "implement_backoff",
                "priority": 1,
                "description": "Implement exponential backoff with longer delays",
                "implementation": {"base_delay": 30, "max_delay": 300, "backoff_factor": 2}
            })
        
        if error_analysis["primary_type"] == "blocked":
            actions.append({
                "action": "rotate_identity",
                "priority": 1,
                "description": "Rotate user agent, IP, and browser fingerprint",
                "implementation": {"new_session": True, "stealth_mode": True}
            })
        
        # Add AI suggestions if available
        if isinstance(ai_suggestions, dict) and "strategies" in ai_suggestions:
            for i, strategy in enumerate(ai_suggestions["strategies"][:3]):
                actions.append({
                    "action": "ai_suggested",
                    "priority": 2 + i,
                    "description": strategy,
                    "implementation": {"ai_generated": True}
                })
        
        return sorted(actions, key=lambda x: x["priority"])
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL"""
        if not url:
            return ""
        
        # Simple domain extraction
        import re
        match = re.search(r'https?://([^/]+)', url)
        return match.group(1) if match else ""
    
    def _get_learned_strategies(self, domain: str) -> List[str]:
        """Get previously successful strategies for a domain"""
        if domain not in self.success_strategies:
            return []
        return self.success_strategies[domain]
    
    def record_success(self, domain: str, strategy: str):
        """Record a successful scraping strategy"""
        if domain not in self.success_strategies:
            self.success_strategies[domain] = []
        
        if strategy not in self.success_strategies[domain]:
            self.success_strategies[domain].append(strategy)
            logger.info(f"Recorded successful strategy '{strategy}' for domain {domain}")
    
    async def detect_captcha_and_waf(self, html_content: str, url: str = "") -> Dict:
        """
        Detect CAPTCHA and WAF protection using AI analysis

        Args:
            html_content: Page HTML content
            url: Page URL for context

        Returns:
            Detection results with bypass strategies
        """
        # Basic pattern detection
        captcha_indicators = {
            "recaptcha": bool(re.search(r'recaptcha|g-recaptcha', html_content, re.IGNORECASE)),
            "hcaptcha": bool(re.search(r'hcaptcha|h-captcha', html_content, re.IGNORECASE)),
            "cloudflare": bool(re.search(r'cloudflare|cf-ray|__cf_bm', html_content, re.IGNORECASE)),
            "generic_captcha": bool(re.search(r'captcha|verify.?human|prove.?human', html_content, re.IGNORECASE)),
            "rate_limit": bool(re.search(r'rate.?limit|too.?many.?requests|slow.?down', html_content, re.IGNORECASE)),
            "access_denied": bool(re.search(r'access.?denied|forbidden|blocked', html_content, re.IGNORECASE))
        }

        # Get AI analysis for more sophisticated detection
        ai_prompt = f"""
        Analyze this HTML content for anti-bot protection measures:

        URL: {url}
        HTML snippet: {html_content[:1500]}

        Identify:
        1. Type of CAPTCHA or protection (reCAPTCHA, hCaptcha, Cloudflare, custom)
        2. Sophistication level (basic, intermediate, advanced)
        3. Bypass difficulty (easy, moderate, hard, extreme)
        4. Recommended bypass strategies
        5. Alternative approaches if direct bypass fails

        Respond in JSON format with specific recommendations.
        """

        try:
            ai_analysis = await self.ai_client.call_model(
                task_type="scraping",
                prompt=ai_prompt,
                max_tokens=600,
                temperature=0.3
            )

            # Try to parse AI response
            try:
                ai_result = json.loads(ai_analysis)
            except:
                ai_result = {"analysis": ai_analysis, "format": "text"}

        except Exception as e:
            logger.error(f"AI CAPTCHA detection failed: {e}")
            ai_result = {"error": str(e)}

        # Combine results
        detection_result = {
            "url": url,
            "timestamp": time.time(),
            "basic_detection": captcha_indicators,
            "ai_analysis": ai_result,
            "protection_level": self._assess_protection_level(captcha_indicators),
            "bypass_strategies": self._generate_bypass_strategies(captcha_indicators, ai_result),
            "success_probability": self._estimate_bypass_success(captcha_indicators)
        }

        return detection_result

    def _assess_protection_level(self, indicators: Dict) -> str:
        """Assess overall protection level"""
        if indicators.get("cloudflare") and (indicators.get("recaptcha") or indicators.get("hcaptcha")):
            return "extreme"
        elif indicators.get("cloudflare") or indicators.get("recaptcha") or indicators.get("hcaptcha"):
            return "high"
        elif indicators.get("generic_captcha") or indicators.get("rate_limit"):
            return "moderate"
        elif indicators.get("access_denied"):
            return "basic"
        else:
            return "minimal"

    def _generate_bypass_strategies(self, indicators: Dict, ai_analysis: Dict) -> List[Dict]:
        """Generate bypass strategies based on detected protection"""
        strategies = []

        # Cloudflare bypass strategies
        if indicators.get("cloudflare"):
            strategies.append({
                "name": "cloudflare_bypass",
                "priority": 1,
                "description": "Use stealth techniques to bypass Cloudflare",
                "implementation": {
                    "method": "playwright_stealth",
                    "wait_time": 15,
                    "user_agent": "random_mobile",
                    "viewport": "random",
                    "javascript_enabled": True,
                    "solve_challenges": True
                },
                "success_rate": 0.6
            })

        # reCAPTCHA strategies
        if indicators.get("recaptcha"):
            strategies.append({
                "name": "recaptcha_avoidance",
                "priority": 2,
                "description": "Avoid triggering reCAPTCHA through behavior modification",
                "implementation": {
                    "method": "human_simulation",
                    "mouse_movements": True,
                    "typing_delays": True,
                    "scroll_behavior": True,
                    "session_persistence": True
                },
                "success_rate": 0.4
            })

        # Rate limiting bypass
        if indicators.get("rate_limit"):
            strategies.append({
                "name": "rate_limit_bypass",
                "priority": 1,
                "description": "Implement intelligent rate limiting and session management",
                "implementation": {
                    "method": "adaptive_delays",
                    "base_delay": 30,
                    "max_delay": 300,
                    "session_rotation": True,
                    "proxy_rotation": False  # Not implemented yet
                },
                "success_rate": 0.8
            })

        # Generic protection bypass
        if not any(indicators.values()):
            strategies.append({
                "name": "standard_stealth",
                "priority": 1,
                "description": "Standard stealth techniques for general protection",
                "implementation": {
                    "method": "basic_stealth",
                    "wait_time": 5,
                    "user_agent_rotation": True,
                    "header_randomization": True
                },
                "success_rate": 0.9
            })

        # Add AI-suggested strategies if available
        if isinstance(ai_analysis, dict) and "bypass_strategies" in ai_analysis:
            for strategy in ai_analysis["bypass_strategies"][:2]:  # Limit to 2 AI strategies
                strategies.append({
                    "name": "ai_suggested",
                    "priority": 3,
                    "description": strategy,
                    "implementation": {"ai_generated": True},
                    "success_rate": 0.5
                })

        return sorted(strategies, key=lambda x: (x["priority"], -x["success_rate"]))

    def _estimate_bypass_success(self, indicators: Dict) -> float:
        """Estimate probability of successful bypass"""
        if indicators.get("cloudflare") and indicators.get("recaptcha"):
            return 0.2  # Very difficult
        elif indicators.get("cloudflare") or indicators.get("recaptcha"):
            return 0.4  # Difficult
        elif indicators.get("rate_limit"):
            return 0.7  # Moderate
        elif indicators.get("generic_captcha"):
            return 0.6  # Moderate
        else:
            return 0.9  # Easy

    async def implement_bypass_strategy(self, strategy: Dict, playwright_page = None) -> Dict:
        """
        Implement a specific bypass strategy

        Args:
            strategy: Strategy configuration from bypass_strategies
            playwright_page: Playwright page object if available

        Returns:
            Implementation result
        """
        strategy_name = strategy.get("name", "unknown")
        implementation = strategy.get("implementation", {})

        result = {
            "strategy": strategy_name,
            "timestamp": time.time(),
            "success": False,
            "actions_taken": [],
            "error": None
        }

        try:
            if strategy_name == "cloudflare_bypass":
                result["actions_taken"] = await self._implement_cloudflare_bypass(implementation, playwright_page)
            elif strategy_name == "rate_limit_bypass":
                result["actions_taken"] = await self._implement_rate_limit_bypass(implementation)
            elif strategy_name == "recaptcha_avoidance":
                result["actions_taken"] = await self._implement_recaptcha_avoidance(implementation, playwright_page)
            elif strategy_name == "standard_stealth":
                result["actions_taken"] = await self._implement_standard_stealth(implementation, playwright_page)
            else:
                result["actions_taken"] = ["Strategy not implemented yet"]

            result["success"] = True

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Bypass strategy {strategy_name} failed: {e}")

        return result

    async def _implement_cloudflare_bypass(self, config: Dict, page = None) -> List[str]:
        """Implement Cloudflare bypass techniques"""
        actions = []

        if page:
            # Wait for Cloudflare challenge
            actions.append("Waiting for Cloudflare challenge resolution")
            await asyncio.sleep(config.get("wait_time", 15))

            # Check if challenge was solved
            try:
                await page.wait_for_selector("body", timeout=5000)
                actions.append("Cloudflare challenge appears to be resolved")
            except:
                actions.append("Cloudflare challenge may still be active")
        else:
            actions.append("No page object provided - cannot implement Cloudflare bypass")

        return actions

    async def _implement_rate_limit_bypass(self, config: Dict) -> List[str]:
        """Implement rate limiting bypass"""
        actions = []

        delay = config.get("base_delay", 30)
        actions.append(f"Implementing {delay}s delay for rate limit bypass")
        await asyncio.sleep(delay)

        if config.get("session_rotation", False):
            actions.append("Session rotation recommended (not implemented)")

        return actions

    async def _implement_recaptcha_avoidance(self, config: Dict, page = None) -> List[str]:
        """Implement reCAPTCHA avoidance techniques"""
        actions = []

        if page and config.get("mouse_movements", False):
            # Simulate human-like mouse movements
            actions.append("Simulating human-like mouse movements")
            try:
                await page.mouse.move(100, 100)
                await asyncio.sleep(0.5)
                await page.mouse.move(200, 150)
                await asyncio.sleep(0.3)
            except:
                actions.append("Mouse movement simulation failed")

        if config.get("scroll_behavior", False):
            actions.append("Implementing natural scrolling behavior")
            # Would implement scrolling here

        return actions

    async def _implement_standard_stealth(self, config: Dict, page = None) -> List[str]:
        """Implement standard stealth techniques"""
        actions = []

        wait_time = config.get("wait_time", 5)
        actions.append(f"Implementing {wait_time}s stealth delay")
        await asyncio.sleep(wait_time)

        if config.get("user_agent_rotation", False):
            actions.append("User agent rotation recommended")

        if config.get("header_randomization", False):
            actions.append("Header randomization recommended")

        return actions

    def get_statistics(self) -> Dict:
        """Get scraping assistant statistics"""
        total_attempts = sum(len(attempts) for attempts in self.attempt_history.values())
        successful_attempts = sum(
            len([a for a in attempts if a.success])
            for attempts in self.attempt_history.values()
        )

        return {
            "total_attempts": total_attempts,
            "successful_attempts": successful_attempts,
            "success_rate": successful_attempts / total_attempts if total_attempts > 0 else 0,
            "domains_learned": len(self.learned_patterns),
            "strategies_learned": sum(len(strategies) for strategies in self.success_strategies.values())
        }
