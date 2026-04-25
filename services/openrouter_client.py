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
        "google/gemini-3.1-flash-lite-preview": ModelConfig(
            "google/gemini-3.1-flash-lite-preview", ModelTier.FAST, 32768, 0.001, 1.8, 0.96
        ),
        "x-ai/grok-4.20-beta": ModelConfig(
            "x-ai/grok-4.20-beta", ModelTier.BALANCED, 32768, 0.01, 3.0, 0.97
        ),
        "openai/gpt-5.4": ModelConfig(
            "openai/gpt-5.4", ModelTier.PREMIUM, 128000, 0.03, 4.2, 0.99
        ),
    }

    # DeepSeek-specific rate-limit policy constants
    DEEPSEEK_MAX_RATE_LIMIT_RETRIES = 2
    DEEPSEEK_RETRY_AFTER_CAP_SECONDS = 45.0
    DEEPSEEK_MAX_DELAY_SECONDS = 60.0

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
        self.allowed_models = self._resolve_allowed_models()
        self.default_model = self._resolve_default_model()

        # Model selection preferences aligned with the admin workflow
        self.preferred_models = {
            "scraping": "x-ai/grok-4.20-beta",
            "analysis": "openai/gpt-5.4",
            "betting": "openai/gpt-5.4",
            "general": "x-ai/grok-4.20-beta",
            "fallback": "google/gemini-3.1-flash-lite-preview",
        }
        if self.default_model:
            for task_type in ("scraping", "analysis", "betting", "general"):
                self.preferred_models[task_type] = self.default_model
        
    def _get_api_key_from_env(self) -> Optional[str]:
        """Get API key from environment variables"""
        import os
        return (
            os.getenv('TRACKSTAR_OPENROUTER_API_KEY')
            or os.getenv('DELMAR_OPENROUTER_API_KEY')
            or os.getenv('OPENROUTER_API_KEY')
        )

    @staticmethod
    def _is_deepseek_model(model: Optional[str]) -> bool:
        """Return True if the model identifier belongs to the DeepSeek family."""
        return bool(model and "deepseek" in model.lower())

    @staticmethod
    def _parse_retry_after(value: Optional[str]) -> Optional[float]:
        """Parse an HTTP Retry-After header value into seconds."""
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    @staticmethod
    def _truncate_error_body(text: str, limit: int = 500) -> str:
        """Truncate a raw error body to a safe logging length."""
        if not text:
            return "(empty body)"
        if len(text) <= limit:
            return text
        return text[:limit] + "..."

    @classmethod
    def _should_fail_fast_rate_limit(
        cls,
        model: Optional[str],
        response_body: str,
        retry_after: Optional[float],
        attempt: int,
    ) -> bool:
        """Decide whether a 429 should fail immediately without further retries."""
        if not cls._is_deepseek_model(model):
            return False
        # DeepSeek-specific: only allow up to DEEPSEEK_MAX_RATE_LIMIT_RETRIES attempts total.
        # attempt is 0-based, so attempt + 1 >= DEEPSEEK_MAX_RATE_LIMIT_RETRIES means we're done.
        if attempt + 1 >= cls.DEEPSEEK_MAX_RATE_LIMIT_RETRIES:
            return True
        # If Retry-After is present but unreasonably large, fail fast to avoid multi-minute hangs.
        if retry_after is not None and retry_after > cls.DEEPSEEK_RETRY_AFTER_CAP_SECONDS:
            return True
        return False

    @classmethod
    def _rate_limit_failure_detail(
        cls,
        model: Optional[str],
        response_body: str,
        retry_after: Optional[float],
    ) -> str:
        """Build a human-friendly failure_detail string for a 429 response."""
        parts: List[str] = []
        if cls._is_deepseek_model(model):
            parts.append(
                f"OpenRouter rate limited {model} for this request shape. "
                "Try again later, reduce output size, or switch to Grok/GPT for this run."
            )
        else:
            parts.append("OpenRouter API rate limit was reached.")

        if retry_after is not None:
            parts.append(f"OpenRouter suggested retrying after {retry_after:.0f} seconds.")

        excerpt = cls._truncate_error_body(response_body, limit=400)
        parts.append(f"429 body excerpt: {excerpt}")
        return " ".join(parts)

    @classmethod
    def _should_use_response_healing(cls, model: Optional[str]) -> bool:
        """Return whether response-healing plugin should be used for the model.

        DeepSeek models are prone to 429s under heavy plugin load; skip
        response-healing for them to reduce routing overhead.
        """
        return not cls._is_deepseek_model(model)

    def _get_ai_config(self):
        return getattr(self.config, 'ai', None)

    def _resolve_allowed_models(self) -> List[str]:
        ai_config = self._get_ai_config()
        configured_models = getattr(ai_config, 'available_models', None)
        candidates = configured_models if isinstance(configured_models, list) and configured_models else list(self.MODELS.keys())
        allowed_models: List[str] = []
        for candidate in candidates:
            model = str(candidate).strip()
            if model and model not in allowed_models:
                allowed_models.append(model)
        return allowed_models or list(self.MODELS.keys())

    def _resolve_default_model(self) -> str:
        ai_config = self._get_ai_config()
        configured_default = getattr(ai_config, 'default_model', None)
        if configured_default and self._is_model_allowed(configured_default):
            return configured_default
        return self.allowed_models[0]

    def _is_model_allowed(self, model: Optional[str]) -> bool:
        base_model = (model or "").split(":", 1)[0]
        return any(base_model == allowed.split(":", 1)[0] for allowed in self.allowed_models)
    
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
            tier_models = [
                name for name in self.allowed_models
                if (config := self._get_model_config(name)) and config.tier == tier
            ]
            if tier_models:
                return max(tier_models, key=lambda m: self.MODELS[m].reliability_score)

        # Use task-specific preferences
        preferred = self.preferred_models.get(task_type, "x-ai/grok-4.20-beta")
        if self._is_model_allowed(preferred):
            return preferred
        return self.default_model

    def _calculate_timeout_seconds(
        self,
        *,
        model_config: Optional[ModelConfig],
        max_tokens: int,
        plugins: Optional[List[Dict[str, Any]]] = None,
        context_size_chars: int = 0,
    ) -> int:
        """Adapt timeout budget to heavier requests such as web-search card structuring."""
        timeout_seconds = 45

        if model_config:
            timeout_seconds = max(timeout_seconds, int(model_config.avg_response_time * 12))

        timeout_seconds += min(60, max(0, int(max_tokens / 150)))

        if plugins:
            timeout_seconds += 30

        if context_size_chars > 0:
            timeout_seconds += min(30, max(0, int(context_size_chars / 1500) * 5))

        return min(180, max(45, timeout_seconds))

    async def call_model(self, model: str = None, prompt: str = "", context: Dict = None,
                        max_tokens: int = None, temperature: float = 0.7,
                        task_type: str = "general", tier: ModelTier = None,
                        plugins: Optional[List[Dict[str, Any]]] = None,
                        return_metadata: bool = False,
                        response_format: Optional[Dict[str, Any]] = None) -> Union[str, Dict[str, Any]]:
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
            plugins: Optional OpenRouter plugins, such as [{"id": "web"}]
            return_metadata: When True, return response content plus metadata
            response_format: Optional structured-output request payload for OpenRouter

        Returns:
            Model response text or response metadata
        """
        if not self.api_key:
            logger.warning("OpenRouter API key not configured, returning fallback response")
            return self._build_fallback_result(
                prompt,
                context,
                task_type,
                model,
                tier,
                return_metadata,
                failure_reason="missing_api_key",
                failure_detail="OpenRouter API key is not configured",
            )

        # Auto-select model if not specified
        if not model:
            model = self.get_optimal_model(task_type, tier)
        elif not self._is_model_allowed(model):
            model = self.default_model

        # Use model-specific defaults
        model_config = self._get_model_config(model)
        if model_config and max_tokens is None:
            max_tokens = min(1000, model_config.max_tokens // 2)  # Conservative default
        elif max_tokens is None:
            max_tokens = 1000
        
        response_format_disabled = False

        # Implement retry logic with exponential backoff
        for attempt in range(self.retry_config["max_retries"] + 1):
            try:
                start_time = time.time()

                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://trackstarai.local",
                    "X-Title": "TrackStarAI"
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

                active_response_format = None if response_format_disabled else response_format
                active_plugins = self._build_request_plugins(
                    model=model,
                    plugins=plugins,
                    response_format=active_response_format,
                )
                if active_response_format:
                    payload["response_format"] = active_response_format

                context_str = ""
                if context:
                    context_str = json.dumps(context, indent=2)

                if active_plugins:
                    payload["plugins"] = active_plugins

                # Add context if provided
                if context_str:
                    payload["messages"][0]["content"] += f"\n\nContext data:\n{context_str}"

                # ── TRACE LOGGING: exact outbound payload ──
                logger.info(
                    "🔵 OPENROUTER REQUEST TRACE | model=%s | task_type=%s | "
                    "plugins=%s | response_format=%s | max_tokens=%d | temp=%.2f | attempt=%d",
                    model,
                    task_type,
                    json.dumps(active_plugins) if active_plugins else "none",
                    json.dumps(active_response_format) if active_response_format else "none",
                    max_tokens,
                    temperature,
                    attempt + 1,
                )

                if not self.session:
                    self.session = aiohttp.ClientSession()

                timeout_seconds = self._calculate_timeout_seconds(
                    model_config=model_config,
                    max_tokens=max_tokens,
                    plugins=active_plugins,
                    context_size_chars=len(context_str),
                )

                async with self.session.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout_seconds)
                ) as response:

                    response_time = time.time() - start_time

                    if response.status == 200:
                        result = await response.json()
                        parsed_response = self._parse_chat_completion_response(result, requested_model=model)
                        response_text = parsed_response["content"]

                        # Track successful request
                        estimated_tokens = len(response_text.split()) * 1.3  # Rough estimate
                        estimated_cost = (estimated_tokens / 1000) * (model_config.cost_per_1k_tokens if model_config else 0.02)
                        self.usage_tracker.record_request(int(estimated_tokens), estimated_cost, response_time, True)

                        # ── TRACE LOGGING: response metadata ──
                        logger.info(
                            "🟢 OPENROUTER RESPONSE TRACE | requested_model=%s | "
                            "actual_model=%s | provider=%s | response_time=%.2fs | "
                            "usage=%s | annotations_count=%d | content_length=%d",
                            model,
                            parsed_response.get("model", "unknown"),
                            parsed_response.get("provider") or "unknown",
                            response_time,
                            json.dumps(parsed_response.get("usage", {})),
                            len(parsed_response.get("annotations", [])),
                            len(response_text),
                        )
                        if parsed_response.get("annotations"):
                            logger.info(
                                "🔗 OPENROUTER CITATIONS | count=%d | urls=%s",
                                len(parsed_response["annotations"]),
                                json.dumps(
                                    [a.get("url", a.get("url_citation", {}).get("url", "?"))
                                     for a in parsed_response["annotations"][:10]]
                                ),
                            )

                        if return_metadata:
                            return parsed_response
                        return response_text

                    elif response.status == 429:  # Rate limit
                        # ── 429 DIAGNOSTICS ──
                        body_text = await response.text()
                        retry_after_raw = response.headers.get("Retry-After")
                        retry_after = self._parse_retry_after(retry_after_raw)

                        logger.warning(
                            "OpenRouter 429 | model=%s | attempt=%d | "
                            "Retry-After=%s | max_tokens=%s | plugins=%s | "
                            "response_format=%s | body_excerpt=%s",
                            model,
                            attempt + 1,
                            retry_after_raw,
                            max_tokens,
                            active_plugins,
                            active_response_format,
                            self._truncate_error_body(body_text, limit=300),
                        )

                        # Decide whether to fail fast without further retries.
                        if self._should_fail_fast_rate_limit(model, body_text, retry_after, attempt):
                            failure_detail = self._rate_limit_failure_detail(
                                model, body_text, retry_after
                            )
                            self.usage_tracker.record_request(0, 0, response_time, False)
                            return self._build_fallback_result(
                                prompt,
                                context,
                                task_type,
                                model,
                                tier,
                                return_metadata,
                                failure_reason="rate_limited",
                                failure_detail=failure_detail,
                                attempts=attempt + 1,
                                status_code=response.status,
                            )

                        # Determine effective retry budget.
                        is_ds = self._is_deepseek_model(model)
                        max_attempts = (
                            self.DEEPSEEK_MAX_RATE_LIMIT_RETRIES
                            if is_ds
                            else self.retry_config["max_retries"] + 1
                        )

                        if attempt + 1 < max_attempts:
                            if retry_after is not None:
                                delay = retry_after
                            else:
                                delay = self.retry_config["base_delay"] * (
                                    self.retry_config["backoff_factor"] ** attempt
                                )

                            # Cap delay to avoid multi-minute hangs.
                            if is_ds:
                                delay = min(delay, self.DEEPSEEK_MAX_DELAY_SECONDS)
                            else:
                                delay = min(delay, self.retry_config["max_delay"])

                            logger.warning(
                                "Rate limited, retrying in %.1fs (attempt %d/%d)",
                                delay,
                                attempt + 1,
                                max_attempts,
                            )
                            await asyncio.sleep(delay)
                            continue

                        failure_detail = self._rate_limit_failure_detail(
                            model, body_text, retry_after
                        )
                        self.usage_tracker.record_request(0, 0, response_time, False)
                        return self._build_fallback_result(
                            prompt,
                            context,
                            task_type,
                            model,
                            tier,
                            return_metadata,
                            failure_reason="rate_limited",
                            failure_detail=failure_detail,
                            attempts=attempt + 1,
                            status_code=response.status,
                        )

                    else:
                        error_text = await response.text()
                        logger.error(f"OpenRouter API error {response.status}: {error_text}")

                        if active_response_format and self._should_retry_without_response_format(
                            response.status,
                            error_text,
                            active_response_format,
                        ):
                            logger.warning(
                                "OpenRouter model %s rejected response_format; retrying without structured output enforcement",
                                model,
                            )
                            response_format_disabled = True
                            continue

                        # Track failed request
                        self.usage_tracker.record_request(0, 0, response_time, False)

                        if attempt < self.retry_config["max_retries"] and response.status >= 500:
                            # Retry on server errors
                            delay = self.retry_config["base_delay"] * (self.retry_config["backoff_factor"] ** attempt)
                            logger.warning(f"Server error, retrying in {delay:.1f}s (attempt {attempt + 1})")
                            await asyncio.sleep(delay)
                            continue

                        return self._build_fallback_result(
                            prompt,
                            context,
                            task_type,
                            model,
                            tier,
                            return_metadata,
                            failure_reason="http_error",
                            failure_detail=f"OpenRouter API returned status {response.status}",
                            attempts=attempt + 1,
                            status_code=response.status,
                        )

            except asyncio.TimeoutError:
                logger.error(f"OpenRouter API timeout on attempt {attempt + 1}")
                if attempt < self.retry_config["max_retries"]:
                    delay = self.retry_config["base_delay"] * (self.retry_config["backoff_factor"] ** attempt)
                    await asyncio.sleep(delay)
                    continue
                self.usage_tracker.record_request(0, 0, 0, False)
                return self._build_fallback_result(
                    prompt,
                    context,
                    task_type,
                    model,
                    tier,
                    return_metadata,
                    failure_reason="timeout",
                    failure_detail="OpenRouter API request timed out",
                    attempts=attempt + 1,
                )

            except Exception as e:
                logger.error(f"OpenRouter API call failed on attempt {attempt + 1}: {e}")
                if attempt < self.retry_config["max_retries"]:
                    delay = self.retry_config["base_delay"] * (self.retry_config["backoff_factor"] ** attempt)
                    await asyncio.sleep(delay)
                    continue
                self.usage_tracker.record_request(0, 0, 0, False)
                return self._build_fallback_result(
                    prompt,
                    context,
                    task_type,
                    model,
                    tier,
                    return_metadata,
                    failure_reason="request_failed",
                    failure_detail=str(e),
                    attempts=attempt + 1,
                )

        # All retries exhausted
        return self._build_fallback_result(
            prompt,
            context,
            task_type,
            model,
            tier,
            return_metadata,
            failure_reason="retry_exhausted",
            failure_detail="OpenRouter request failed after all retry attempts",
            attempts=self.retry_config["max_retries"] + 1,
        )

    def _build_request_plugins(
        self,
        *,
        model: Optional[str],
        plugins: Optional[List[Dict[str, Any]]],
        response_format: Optional[Dict[str, Any]],
    ) -> Optional[List[Dict[str, Any]]]:
        active_plugins = [
            dict(plugin)
            for plugin in (plugins or [])
            if isinstance(plugin, dict) and plugin.get("id")
        ]

        if (
            response_format
            and self._should_use_response_healing(model)
            and not any(plugin.get("id") == "response-healing" for plugin in active_plugins)
        ):
            active_plugins.append({"id": "response-healing"})

        return active_plugins or None

    def _should_retry_without_response_format(
        self,
        status_code: int,
        error_text: str,
        response_format: Optional[Dict[str, Any]],
    ) -> bool:
        if not response_format or status_code not in {400, 404, 415, 422}:
            return False

        normalized_error = (error_text or "").lower()
        response_format_terms = (
            "response_format",
            "json_object",
            "json schema",
            "json_schema",
            "structured output",
            "structured outputs",
        )
        rejection_terms = (
            "unsupported",
            "not supported",
            "does not support",
            "only supported",
            "invalid",
            "unknown",
            "unrecognized",
            "not available",
            "not allowed",
            "cannot",
        )

        return any(term in normalized_error for term in response_format_terms) and any(
            term in normalized_error for term in rejection_terms
        )

    def _get_model_config(self, model: Optional[str]) -> Optional[ModelConfig]:
        """Resolve model config even when the requested model has a suffix."""
        base_model = (model or "").split(":", 1)[0]
        return self.MODELS.get(base_model)

    def _build_fallback_result(
        self,
        prompt: str,
        context: Dict,
        task_type: str,
        model: Optional[str],
        tier: Optional[ModelTier],
        return_metadata: bool,
        failure_reason: str = "fallback",
        failure_detail: Optional[str] = None,
        attempts: Optional[int] = None,
        status_code: Optional[int] = None,
    ) -> Union[str, Dict[str, Any]]:
        fallback_response = self._generate_fallback_response(prompt, context, task_type)
        if not return_metadata:
            return fallback_response

        return {
            "content": fallback_response,
            "annotations": [],
            "usage": {},
            "model": model or self.get_optimal_model(task_type, tier),
            "provider": None,
            "raw_response": {},
            "fallback": True,
            "failure_reason": failure_reason,
            "failure_detail": failure_detail,
            "attempts": attempts,
            "status_code": status_code,
        }

    def _parse_chat_completion_response(self, result: Dict[str, Any], requested_model: str) -> Dict[str, Any]:
        """Normalize OpenRouter chat completion responses for metadata-aware callers."""
        choices = result.get("choices") or []
        first_choice = choices[0] if choices else {}
        message = first_choice.get("message") if isinstance(first_choice, dict) else {}
        message = message if isinstance(message, dict) else {}

        return {
            "content": self._extract_message_content(message),
            "annotations": self._extract_message_annotations(message),
            "usage": result.get("usage") or {},
            "model": result.get("model") or requested_model,
            "provider": result.get("provider"),
            "raw_response": result,
        }

    def _extract_message_content(self, message: Dict[str, Any]) -> str:
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                parts.append(item.get("text") or item.get("content") or "")
            return "\n".join(part for part in parts if part).strip()
        return str(content or "")

    def _extract_message_annotations(self, message: Dict[str, Any]) -> List[Dict[str, Any]]:
        annotations: List[Dict[str, Any]] = []

        message_annotations = message.get("annotations")
        if isinstance(message_annotations, list):
            annotations.extend(item for item in message_annotations if isinstance(item, dict))

        content = message.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                item_annotations = item.get("annotations")
                if isinstance(item_annotations, list):
                    annotations.extend(annotation for annotation in item_annotations if isinstance(annotation, dict))

        return annotations
    
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
                                initial_predictions: List[Dict],
                                model_override: Optional[str] = None) -> Dict:
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
                model=model_override,
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
            (model, self._get_model_config(model).tier.value)
            for model in self.allowed_models
            if self._get_model_config(model)
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
                "tier": config.tier.value if config else "custom",
                "max_tokens": config.max_tokens if config else None,
                "cost_per_1k": config.cost_per_1k_tokens if config else None,
                "avg_response_time": config.avg_response_time if config else None,
                "reliability": config.reliability_score if config else None
            }
            for name in self.allowed_models
            for config in [self._get_model_config(name)]
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
