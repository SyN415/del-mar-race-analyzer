#!/usr/bin/env python3
"""
TrackStarAI horse racing intelligence application.

Main FastAPI application entry point for the branded web experience,
protected admin workflow, and AI-assisted race-card analysis pipeline.
"""

import asyncio
import hashlib
import json
import hmac
import logging
import os
import secrets
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import uvicorn
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import existing components
from race_prediction_engine import RacePredictionEngine
from scrapers.playwright_equibase_scraper import PlaywrightEquibaseScraper
from config.config_manager import ConfigManager

# Import new services
try:
    from services.session_manager import SessionManager
    from services.openrouter_client import OpenRouterClient
    from services.race_card_admin import (
        AdminRaceCardJSONError,
        build_equibase_card_overview_url,
        build_equibase_race_urls,
        extract_json_object,
        fetch_equibase_expected_horses_by_race,
        fetch_equibase_expected_race_numbers,
        find_missing_horses_by_race,
        find_missing_race_numbers,
        find_races_with_incomplete_fields,
        merge_source_urls,
        merge_structured_race_cards,
        normalize_admin_results,
    )
except ImportError as e:
    print(f"Some services not available: {e}")
    SessionManager = None
    OpenRouterClient = None
    AdminRaceCardJSONError = ValueError
    build_equibase_card_overview_url = None
    build_equibase_race_urls = None
    extract_json_object = None
    fetch_equibase_expected_horses_by_race = None
    fetch_equibase_expected_race_numbers = None
    find_missing_horses_by_race = None
    find_missing_race_numbers = None
    merge_source_urls = None
    merge_structured_race_cards = None
    normalize_admin_results = None

# Configure logging
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Import SmartPick scraper after logger is configured
# Use the fixed Playwright-based SmartPick scraper that handles Angular/JavaScript rendering
try:
    from scrapers.smartpick_playwright import FixedPlaywrightSmartPickScraper as SmartPickRaceScraper
    logger.info("✅ Using fixed Playwright SmartPick scraper with Angular support")
except ImportError as e:
    from scrapers.smartpick_scraper import SmartPickRaceScraper
    logger.warning(f"⚠️  Using fallback SmartPick scraper (may not work with Angular pages): {e}")

# Brand constants
BRAND_NAME = "TrackStarAI"
AUTH_COOKIE_NAME = "trackstar_auth"

# Initialize FastAPI app
app = FastAPI(
    title=BRAND_NAME,
    description="AI-native horse racing intelligence with resilient scraping, structured data, and curated race-card analysis.",
    version="1.0.0"
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static", html=True), name="static")
templates = Jinja2Templates(directory="templates")

# Global application state
class AppState:
    def __init__(self):
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load_config()
        self.session_manager = None
        self.orchestration_service = None
        self.openrouter_client = None
        self.prediction_engine = RacePredictionEngine()
        self.gradient_boosting_predictor = None
        self.kelly_optimizer = None
        self.active_tasks: Dict[str, asyncio.Task] = {}  # Track running tasks
        self._session_manager_lock = asyncio.Lock()
        self._orchestration_service_lock = asyncio.Lock()

    def ensure_openrouter_client(self):
        """Initialize the OpenRouter client only when needed."""
        if self.openrouter_client or not OpenRouterClient:
            return self.openrouter_client

        try:
            self.openrouter_client = OpenRouterClient(self.config)
            logger.info("OpenRouter client initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize OpenRouter client: {e}")

        return self.openrouter_client

    async def ensure_session_manager(self):
        """Initialize persistence only when a route actually needs it."""
        if self.session_manager or not SessionManager:
            return self.session_manager

        async with self._session_manager_lock:
            if self.session_manager:
                return self.session_manager

            try:
                session_manager = SessionManager(config=self.config)
                await session_manager.initialize()
                self.session_manager = session_manager
                logger.info("Session manager initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize session manager on demand: {e}")
                return None

        try:
            asyncio.create_task(self.session_manager.recover_interrupted_sessions())
        except Exception as e:
            logger.warning(f"Failed to schedule interrupted session recovery: {e}")

        return self.session_manager

    async def ensure_orchestration_service(self):
        """Initialize orchestration only for endpoints that need it."""
        if self.orchestration_service:
            return self.orchestration_service

        session_manager = await self.ensure_session_manager()
        if not session_manager:
            return None

        async with self._orchestration_service_lock:
            if self.orchestration_service:
                return self.orchestration_service

            try:
                from services.orchestration_service import OrchestrationService

                self.orchestration_service = OrchestrationService(
                    session_manager=session_manager,
                    prediction_engine=self.prediction_engine,
                    config_manager=self.config_manager,
                )
                logger.info("Orchestration service initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize orchestration service on demand: {e}")
                return None

        return self.orchestration_service
        
    async def initialize(self):
        """Initialize only lightweight services needed for first HTTP readiness."""
        try:
            self.ensure_openrouter_client()
            logger.info("Application state initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize application state: {e}")

# Global app state instance
app_state = AppState()

# ---------------------------------------------------------------------------
# Auth helpers – lightweight HMAC-signed cookie auth (no DB needed)
# ---------------------------------------------------------------------------
_AUTH_SECRET: str | None = None


def _get_auth_secret() -> str:
    """Return the auth secret, falling back to a per-process random value."""
    global _AUTH_SECRET
    if _AUTH_SECRET is None:
        _AUTH_SECRET = (
            app_state.config.web.auth_secret
            or os.getenv("TRACKSTAR_AUTH_SECRET")
            or os.getenv("DELMAR_AUTH_SECRET")
            or secrets.token_hex(32)
        )
    return _AUTH_SECRET


def _get_admin_password() -> str | None:
    return (
        app_state.config.web.admin_password
        or os.getenv("TRACKSTAR_ADMIN_PASSWORD")
        or os.getenv("DELMAR_ADMIN_PASSWORD")
    )


def _has_auth_secret() -> bool:
    return bool(
        app_state.config.web.auth_secret
        or os.getenv("TRACKSTAR_AUTH_SECRET")
        or os.getenv("DELMAR_AUTH_SECRET")
    )


def _sign_value(value: str) -> str:
    secret = _get_auth_secret()
    sig = hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()
    return f"{value}:{sig}"


def _verify_signed(raw: str) -> str | None:
    if ":" not in raw:
        return None
    value, sig = raw.rsplit(":", 1)
    expected = hmac.new(
        _get_auth_secret().encode(), value.encode(), hashlib.sha256
    ).hexdigest()
    if hmac.compare_digest(sig, expected):
        return value
    return None


def _get_current_role(request: Request) -> str | None:
    """Return 'admin' or 'user' from the signed auth cookie, or None."""
    cookie = request.cookies.get(AUTH_COOKIE_NAME)
    if not cookie:
        return None
    return _verify_signed(cookie)


def _is_admin(request: Request) -> bool:
    return _get_current_role(request) == "admin"


def _auth_enabled() -> bool:
    """Auth is active only when both the password and signing secret are configured."""
    return bool(_get_admin_password() and _has_auth_secret())


def _admin_access_message() -> str:
    return (
        "Admin access is not configured on this deployment yet. "
        "Set TRACKSTAR_ADMIN_PASSWORD and TRACKSTAR_AUTH_SECRET to enable it."
    )


def _template_context(request: Request, title: str, **extra):
    context = {
        "request": request,
        "title": title,
        "brand_name": BRAND_NAME,
        "auth_enabled": _auth_enabled(),
        "setup_required": not _auth_enabled(),
        "admin_access_message": _admin_access_message(),
        "user_role": _get_current_role(request),
    }
    context.update(extra)
    return context


def _render_login_page(
    request: Request,
    *,
    error: str | None = None,
    title: str = "TrackStarAI Admin Sign In",
):
    return templates.TemplateResponse(
        request,
        "login.html",
        _template_context(
            request,
            title,
            error=error,
            configuration_hint=None if _auth_enabled() else _admin_access_message(),
        ),
    )


MODEL_CATALOG = {
    "google/gemini-3.1-flash-lite-preview": {
        "id": "google/gemini-3.1-flash-lite-preview",
        "label": "Gemini 3.1 Flash Lite Preview",
        "tier_label": "Cheap",
        "description": "Fast, lower-cost option for first-pass structuring.",
    },
    "x-ai/grok-4.20-beta": {
        "id": "x-ai/grok-4.20-beta",
        "label": "Grok 4.20 Beta",
        "tier_label": "Affordable",
        "description": "Balanced option for race-card organization and ranking.",
    },
    "openai/gpt-5.4": {
        "id": "openai/gpt-5.4",
        "label": "GPT-5.4",
        "tier_label": "Best",
        "description": "Highest-quality option for the strongest reasoning pass.",
    },
}


def _humanize_model_id(model_id: str) -> str:
    normalized = (model_id or "").split("/", 1)[-1].replace("-", " ").replace("_", " ").strip()
    if not normalized:
        return model_id or "Custom model"
    return " ".join(part.capitalize() for part in normalized.split())


def _build_model_option(model_id: str) -> Dict[str, str]:
    catalog_entry = MODEL_CATALOG.get(model_id)
    if catalog_entry:
        return dict(catalog_entry)
    return {
        "id": model_id,
        "label": _humanize_model_id(model_id),
        "tier_label": "Custom",
        "description": f"Configured via environment variable for OpenRouter routing ({model_id}).",
    }


def _get_ai_config():
    return getattr(app_state.config, "ai", None)


def _get_configured_model_ids() -> List[str]:
    ai_config = _get_ai_config()
    configured_models = getattr(ai_config, "available_models", None)
    if isinstance(configured_models, list) and configured_models:
        normalized_models: List[str] = []
        for configured_model in configured_models:
            model_id = str(configured_model).strip()
            if model_id and model_id not in normalized_models:
                normalized_models.append(model_id)
        if normalized_models:
            return normalized_models
    return list(MODEL_CATALOG.keys())


def _get_configured_model_options() -> List[Dict[str, str]]:
    return [_build_model_option(model_id) for model_id in _get_configured_model_ids()]


def _get_default_model(fallback: str) -> str:
    ai_config = _get_ai_config()
    configured_default = getattr(ai_config, "default_model", None)
    available_models = _get_configured_model_ids()
    if configured_default in available_models:
        return configured_default
    if fallback in available_models:
        return fallback
    return available_models[0]


# Supported tracks — configurable via TRACK_CONFIG env var
# Extended format (recommended):
#   {"DMR": {"name": "Del Mar", "country": "USA"}, "OI": {"name": "Tokyo City Keiba", "country": "JPN"}}
# Legacy format still supported:
#   {"DMR": "Del Mar", "SA": "Santa Anita"}
_DEFAULT_TRACK_CONFIG: Dict[str, Any] = {
    "DMR": {"name": "Del Mar", "country": "USA"},
    "SA": {"name": "Santa Anita", "country": "USA"},
}
try:
    _raw_track_config = json.loads(os.environ.get("TRACK_CONFIG", "")) or _DEFAULT_TRACK_CONFIG
except (json.JSONDecodeError, TypeError):
    _raw_track_config = _DEFAULT_TRACK_CONFIG

# Normalize: support both {"ID": "Name"} and {"ID": {"name": ..., "country": ...}}
TRACK_CONFIG_FULL: Dict[str, Dict[str, str]] = {}
for _tid, _val in _raw_track_config.items():
    if isinstance(_val, dict):
        TRACK_CONFIG_FULL[_tid] = {"name": _val.get("name", _tid), "country": _val.get("country", "USA")}
    else:
        TRACK_CONFIG_FULL[_tid] = {"name": str(_val), "country": "USA"}

# Backward-compatible name lookup: {track_id: display_name}
SUPPORTED_TRACKS: Dict[str, str] = {tid: cfg["name"] for tid, cfg in TRACK_CONFIG_FULL.items()}
# Country lookup: {track_id: country_code}
TRACK_COUNTRIES: Dict[str, str] = {tid: cfg["country"] for tid, cfg in TRACK_CONFIG_FULL.items()}

def get_track_country(track_id: str) -> str:
    """Return the country code for a track (defaults to 'USA')."""
    return TRACK_COUNTRIES.get(track_id, "USA")

def is_international_track(track_id: str) -> bool:
    """Return True if track is outside the USA."""
    return get_track_country(track_id) != "USA"

logger.info(f"Configured tracks: {SUPPORTED_TRACKS}")
logger.info(f"Track countries: {TRACK_COUNTRIES}")

MODEL_OPTIONS = [MODEL_CATALOG[model_id] for model_id in MODEL_CATALOG]
MODEL_LOOKUP = MODEL_CATALOG
DEFAULT_LLM_MODEL = "x-ai/grok-4.20-beta"
DEFAULT_ADMIN_LLM_MODEL = "x-ai/grok-4.20-beta"
ADMIN_WEB_SEARCH_INITIAL_MAX_TOKENS = 16000
ADMIN_WEB_SEARCH_RETRY_MAX_TOKENS = 8000
ADMIN_COMPACT_JSON_RETRY_MODEL_PREFIXES = ("minimax/",)
ADMIN_MANUAL_MAX_TOKENS = 2500
ADMIN_DEEP_DIVE_MAX_TOKENS = 12000
STATUS_BADGE_CLASSES = {
    "completed": "success",
    "running": "primary",
    "created": "secondary",
    "failed": "danger",
    "cancelled": "secondary",
    "interrupted": "warning",
}

# Pydantic models for API requests
class AnalysisRequest(BaseModel):
    date: str  # Format: YYYY-MM-DD
    llm_model: str = Field(default_factory=lambda: _get_default_model(DEFAULT_LLM_MODEL))
    track_id: str = "DMR"  # DMR (Del Mar) or SA (Santa Anita)


class AdminRaceCardRequest(BaseModel):
    race_date: str
    track_id: str = "DMR"
    llm_model: str = Field(default_factory=lambda: _get_default_model(DEFAULT_ADMIN_LLM_MODEL))
    source_mode: Literal["web_search", "manual"] = "web_search"
    source_text: str = ""
    source_urls: List[str] = Field(default_factory=list)
    admin_notes: str = ""

class AdminDeepDiveRequest(BaseModel):
    session_id: str
    race_number: int
    race_date: str
    track_id: str = "DMR"
    force_refresh: bool = False

class CuratedCardRequest(BaseModel):
    race_date: str
    track_id: str = "DMR"
    session_id: str
    top_pick: Optional[Dict] = None
    value_play: Optional[Dict] = None
    longshot: Optional[Dict] = None
    admin_notes: str = ""
    betting_strategy: str = ""
    is_published: bool = False
    races: Optional[List] = None
    card_overview: str = ""

class AutoCurateRequest(BaseModel):
    session_id: str
    race_date: str
    track_id: str = "DMR"

class AnalysisStatus(BaseModel):
    session_id: str
    status: str  # "running", "completed", "failed"
    progress: int  # 0-100
    current_stage: str
    message: str
    results: Optional[Dict] = None

# API Routes
@app.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    """Public landing page showing published curated betting cards."""
    session_manager = await app_state.ensure_session_manager()
    published_cards: List[Dict] = []
    if session_manager:
        try:
            published_cards = await asyncio.wait_for(
                session_manager.get_published_curated_cards(limit=12), timeout=2.0
            )
            for pc in published_cards:
                pc["track_name"] = SUPPORTED_TRACKS.get(pc.get("track_id"), pc.get("track_id"))
                pc["card_url"] = f"/card/{pc.get('race_date')}/{pc.get('track_id')}"
        except Exception as e:
            logger.warning(f"Failed to load published curated cards for landing page: {e}")
    return templates.TemplateResponse(
        request,
        "landing.html",
        _template_context(
            request,
            BRAND_NAME,
            published_curated_cards=published_cards,
        ),
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page for admin access."""
    if _is_admin(request):
        return RedirectResponse("/admin", status_code=302)
    return _render_login_page(request)


@app.post("/login")
async def login_submit(request: Request):
    """Handle login form submission."""
    form = await request.form()
    password = form.get("password", "")
    admin_pw = _get_admin_password()

    if not _auth_enabled() or not admin_pw:
        return _render_login_page(request, error=_admin_access_message())

    if hmac.compare_digest(password, admin_pw):
        response = RedirectResponse("/admin", status_code=302)
        response.set_cookie(
            AUTH_COOKIE_NAME,
            _sign_value("admin"),
            httponly=True,
            samesite="lax",
            secure=str(getattr(app_state.config, "environment", "")).lower() == "production",
            max_age=60 * 60 * 24,  # 24 hours
        )
        return response

    return _render_login_page(request, error="Invalid password. Please try again.")


@app.get("/logout")
async def logout(request: Request):
    """Clear auth cookie and redirect home."""
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie(AUTH_COOKIE_NAME)
    return response


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    """Admin workflow for saving structured race cards with OpenRouter."""
    if not _auth_enabled():
        return _render_login_page(
            request,
            error=_admin_access_message(),
            title="Admin Access Unavailable",
        )
    if not _is_admin(request):
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse(
        request,
        "admin.html",
        _template_context(
            request,
            f"{BRAND_NAME} Admin Workflow",
            available_tracks=[{"id": track_id, "name": track_name} for track_id, track_name in SUPPORTED_TRACKS.items()],
            default_date=datetime.now().strftime("%Y-%m-%d"),
            openrouter_configured=bool(app_state.ensure_openrouter_client() and app_state.openrouter_client.api_key),
        ),
    )

@app.post("/api/analyze")
async def start_analysis(request: AnalysisRequest, background_tasks: BackgroundTasks):
    """Start race analysis for specified date and track"""
    try:
        logger.info(
            "📥 ENDPOINT HIT: /api/analyze | date=%s | track=%s | llm_model=%s | "
            "web_search=%s",
            request.date,
            request.track_id,
            request.llm_model or "(none)",
            getattr(request, "web_search", "(not in request)"),
        )
        _validate_track_id(request.track_id)
        _validate_llm_model(request.llm_model)

        # Validate date format
        try:
            analysis_date = datetime.strptime(request.date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

        session_manager = await app_state.ensure_session_manager()

        # Create new analysis session
        if session_manager:
            session_id = await session_manager.create_session(
                race_date=request.date,
                llm_model=request.llm_model,
                track_id=request.track_id
            )
        else:
            # Fallback session ID generation
            session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Create and track the background task
        task = asyncio.create_task(
            run_analysis_pipeline(
                session_id=session_id,
                date=request.date,
                llm_model=request.llm_model,
                track_id=request.track_id
            )
        )
        app_state.active_tasks[session_id] = task

        return JSONResponse({
            "session_id": session_id,
            "status": "started",
            "message": f"Analysis started for {request.date}"
        })
        
    except Exception as e:
        logger.error(f"Failed to start analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/race-cards")
async def create_admin_race_card(request: AdminRaceCardRequest, http_request: Request = None):
    """Create a saved race card from manual notes or OpenRouter web search."""
    if not _auth_enabled():
        raise HTTPException(status_code=503, detail="Admin access is not configured on the server")
    if http_request is None or not _is_admin(http_request):
        raise HTTPException(status_code=403, detail="Admin authentication required")

    session_manager = await app_state.ensure_session_manager()
    openrouter_client = app_state.ensure_openrouter_client()

    if not session_manager:
        raise HTTPException(status_code=503, detail="Session manager is not available")
    if not openrouter_client or not openrouter_client.api_key:
        raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY is not configured on the server")
    if (
        not build_equibase_card_overview_url
        or not extract_json_object
        or not fetch_equibase_expected_horses_by_race
        or not fetch_equibase_expected_race_numbers
        or not find_missing_horses_by_race
        or not find_missing_race_numbers
        or not merge_source_urls
        or not merge_structured_race_cards
        or not normalize_admin_results
    ):
        raise HTTPException(status_code=503, detail="Admin race-card helpers are unavailable")

    logger.info(
        "📥 ENDPOINT HIT: /api/admin/race-cards | date=%s | track=%s | llm_model=%s | "
        "source_mode=%s | web_search=%s",
        request.race_date,
        request.track_id,
        request.llm_model or "(none)",
        request.source_mode,
        getattr(request, "web_search", "(not in request)"),
    )

    _validate_track_id(request.track_id)
    _validate_llm_model(request.llm_model)

    try:
        datetime.strptime(request.race_date, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD") from exc

    source_text = (request.source_text or "").strip()
    if request.source_mode == "manual" and not source_text:
        raise HTTPException(status_code=400, detail="Source text is required in manual mode")

    started_at = time.perf_counter()
    session_id = await session_manager.create_session(
        race_date=request.race_date,
        llm_model=request.llm_model,
        track_id=request.track_id,
    )

    def extract_admin_openrouter_payload(
        openrouter_response: object,
        *,
        phase_label: str,
    ) -> Dict[str, object]:
        if not isinstance(openrouter_response, dict):
            raise HTTPException(
                status_code=502,
                detail=f"OpenRouter returned an unexpected response format while {phase_label}.",
            )

        if openrouter_response.get("fallback"):
            failure_reason = str(openrouter_response.get("failure_reason") or "fallback")
            failure_detail = str(openrouter_response.get("failure_detail") or "").strip()
            attempts = openrouter_response.get("attempts")

            if failure_reason == "timeout":
                attempts_suffix = f" after {attempts} attempts" if attempts else ""
                detail = (
                    f"OpenRouter timed out while {phase_label}{attempts_suffix}. "
                    "Please try again in a moment."
                )
            elif failure_reason == "rate_limited":
                detail = f"OpenRouter rate limited the request while {phase_label}. Please retry shortly."
            else:
                detail = f"OpenRouter was unavailable while {phase_label}."

            if failure_detail and failure_detail not in detail:
                detail = f"{detail} {failure_detail}"

            raise HTTPException(status_code=503, detail=detail)

        try:
            return extract_json_object(openrouter_response.get("content", ""))
        except AdminRaceCardJSONError as exc:
            model_name = str(openrouter_response.get("model") or request.llm_model)
            logger.error(
                "Admin race-card JSON parse failed while %s using %s: %s",
                phase_label,
                model_name,
                exc.diagnostic_message,
            )
            raise

    try:
        is_web_search_mode = request.source_mode == "web_search"
        track_country = get_track_country(request.track_id)
        admin_response_format = {"type": "json_object"}
        official_card_url = (
            build_equibase_card_overview_url(request.track_id, request.race_date, country=track_country)
            if is_web_search_mode
            else None
        )
        expected_horses_by_race = (
            fetch_equibase_expected_horses_by_race(request.track_id, request.race_date, country=track_country)
            if is_web_search_mode
            else {}
        )
        expected_race_numbers = (
            fetch_equibase_expected_race_numbers(request.track_id, request.race_date, country=track_country)
            if is_web_search_mode
            else []
        )
        if expected_horses_by_race and not expected_race_numbers:
            expected_race_numbers = sorted(expected_horses_by_race)
        per_race_urls = (
            build_equibase_race_urls(request.track_id, request.race_date, expected_race_numbers, country=track_country)
            if is_web_search_mode and expected_race_numbers and build_equibase_race_urls
            else {}
        )
        status_message = (
            "Auto-gathering and structuring race card with OpenRouter web search"
            if is_web_search_mode
            else "Structuring race card from manual source material"
        )
        await session_manager.update_session_status(
            session_id, "running", 25, "admin_structuring", status_message
        )

        openrouter_response = await openrouter_client.call_model(
            model=request.llm_model,
            task_type="analysis",
            prompt=_build_admin_structuring_prompt(
                request,
                expected_race_numbers=expected_race_numbers,
                expected_horses_by_race=expected_horses_by_race,
                official_card_url=official_card_url,
                per_race_urls=per_race_urls,
            ),
            context=_build_admin_structuring_context(
                request,
                source_text,
                expected_race_numbers=expected_race_numbers,
                expected_horses_by_race=expected_horses_by_race,
                official_card_url=official_card_url,
                per_race_urls=per_race_urls,
            ),
            max_tokens=(
                ADMIN_WEB_SEARCH_INITIAL_MAX_TOKENS
                if is_web_search_mode
                else ADMIN_MANUAL_MAX_TOKENS
            ),
            temperature=0.2,
            plugins=[{"id": "web"}] if is_web_search_mode else None,
            return_metadata=True,
            response_format=admin_response_format,
        )
        merged_urls = merge_source_urls(
            source_urls=request.source_urls + ([official_card_url] if official_card_url else []),
            annotations=openrouter_response.get("annotations"),
        )
        try:
            structured_payload = extract_admin_openrouter_payload(
                openrouter_response,
                phase_label="structuring the admin race card",
            )
        except AdminRaceCardJSONError as exc:
            model_name = (
                str(openrouter_response.get("model") or request.llm_model)
                if isinstance(openrouter_response, dict)
                else request.llm_model
            )
            if not _should_retry_admin_json_with_compact_prompt(request, model_name):
                raise _build_admin_json_http_exception(
                    request,
                    openrouter_response,
                    phase_label="structuring the admin race card",
                    exc=exc,
                ) from exc

            await session_manager.update_session_status(
                session_id,
                "running",
                45,
                "admin_retry_malformed_json",
                f"Retrying malformed JSON from {model_name} with a compact schema",
            )
            retry_response = await openrouter_client.call_model(
                model=request.llm_model,
                task_type="analysis",
                prompt=_build_admin_structuring_prompt(
                    request,
                    expected_race_numbers=expected_race_numbers,
                    expected_horses_by_race=expected_horses_by_race,
                    official_card_url=official_card_url,
                    per_race_urls=per_race_urls,
                    compact_response=True,
                ),
                context=_build_admin_structuring_context(
                    request,
                    source_text,
                    expected_race_numbers=expected_race_numbers,
                    expected_horses_by_race=expected_horses_by_race,
                    official_card_url=official_card_url,
                    per_race_urls=per_race_urls,
                ),
                max_tokens=ADMIN_WEB_SEARCH_INITIAL_MAX_TOKENS,
                temperature=0.2,
                plugins=[{"id": "web"}],
                return_metadata=True,
                response_format=admin_response_format,
            )
            merged_urls = merge_source_urls(
                source_urls=merged_urls,
                annotations=retry_response.get("annotations"),
            )
            try:
                structured_payload = extract_admin_openrouter_payload(
                    retry_response,
                    phase_label="retrying malformed admin race-card JSON",
                )
            except AdminRaceCardJSONError as retry_exc:
                raise _build_admin_json_http_exception(
                    request,
                    retry_response,
                    phase_label="retrying malformed admin race-card JSON",
                    exc=retry_exc,
                ) from retry_exc

        final_structured_payload = structured_payload
        missing_race_numbers = (
            find_missing_race_numbers(final_structured_payload, expected_race_numbers)
            if expected_race_numbers
            else []
        )
        missing_horses_by_race = _filter_missing_horses_by_race(
            find_missing_horses_by_race(final_structured_payload, expected_horses_by_race),
            excluded_race_numbers=missing_race_numbers,
        )

        if is_web_search_mode and (missing_race_numbers or missing_horses_by_race):
            retry_details: List[str] = []
            if missing_race_numbers:
                retry_details.append(
                    f"missing races: {', '.join(str(number) for number in missing_race_numbers)}"
                )
            if missing_horses_by_race:
                retry_details.append(f"missing horses: {_format_missing_horses_by_race(missing_horses_by_race)}")
            await session_manager.update_session_status(
                session_id,
                "running",
                60,
                "admin_retry_incomplete_card",
                f"Retrying incomplete card for {'; '.join(retry_details)}",
            )

            retry_response = await openrouter_client.call_model(
                model=request.llm_model,
                task_type="analysis",
                prompt=_build_admin_structuring_prompt(
                    request,
                    expected_race_numbers=expected_race_numbers,
                    missing_race_numbers=missing_race_numbers,
                    expected_horses_by_race=expected_horses_by_race,
                    missing_horses_by_race=missing_horses_by_race,
                    official_card_url=official_card_url,
                    per_race_urls=per_race_urls,
                ),
                context=_build_admin_structuring_context(
                    request,
                    source_text,
                    expected_race_numbers=expected_race_numbers,
                    missing_race_numbers=missing_race_numbers,
                    expected_horses_by_race=expected_horses_by_race,
                    missing_horses_by_race=missing_horses_by_race,
                    official_card_url=official_card_url,
                    per_race_urls=per_race_urls,
                ),
                max_tokens=ADMIN_WEB_SEARCH_RETRY_MAX_TOKENS,
                temperature=0.2,
                plugins=[{"id": "web"}],
                return_metadata=True,
                response_format=admin_response_format,
            )
            retry_payload = extract_admin_openrouter_payload(
                retry_response,
                phase_label="retrying the incomplete admin race card",
            )
            final_structured_payload = merge_structured_race_cards(structured_payload, retry_payload)
            merged_urls = merge_source_urls(
                source_urls=merged_urls,
                annotations=retry_response.get("annotations"),
            )
            missing_race_numbers = find_missing_race_numbers(final_structured_payload, expected_race_numbers)
            missing_horses_by_race = _filter_missing_horses_by_race(
                find_missing_horses_by_race(final_structured_payload, expected_horses_by_race),
                excluded_race_numbers=missing_race_numbers,
            )

        # --- Jockey / trainer gap-fill retry ---
        incomplete_field_races = (
            find_races_with_incomplete_fields(final_structured_payload)
            if is_web_search_mode
            else {}
        )
        if incomplete_field_races:
            incomplete_race_nums = sorted(incomplete_field_races)
            gap_summary = "; ".join(
                f"Race {rn}: {len(gaps)} horse(s)" for rn, gaps in sorted(incomplete_field_races.items())
            )
            logger.info(f"Detected incomplete jockey/trainer fields — retrying for {gap_summary}")
            await session_manager.update_session_status(
                session_id,
                "running",
                75,
                "admin_retry_jockey_trainer",
                f"Filling missing jockey/trainer data for races {', '.join(str(n) for n in incomplete_race_nums)}",
            )
            # Build per-race URLs filtered to only the incomplete races
            incomplete_per_race_urls = {
                rn: per_race_urls[rn] for rn in incomplete_race_nums if rn in per_race_urls
            } if per_race_urls else {}

            jt_retry_response = await openrouter_client.call_model(
                model=request.llm_model,
                task_type="analysis",
                prompt=_build_jockey_trainer_retry_prompt(
                    request,
                    incomplete_field_races=incomplete_field_races,
                    per_race_urls=incomplete_per_race_urls,
                ),
                context=_build_admin_structuring_context(
                    request,
                    source_text,
                    expected_race_numbers=incomplete_race_nums,
                    official_card_url=official_card_url,
                    per_race_urls=incomplete_per_race_urls,
                ),
                max_tokens=ADMIN_WEB_SEARCH_RETRY_MAX_TOKENS,
                temperature=0.2,
                plugins=[{"id": "web"}],
                return_metadata=True,
                response_format=admin_response_format,
            )
            try:
                jt_retry_payload = extract_admin_openrouter_payload(
                    jt_retry_response,
                    phase_label="retrying jockey/trainer gap-fill",
                )
                final_structured_payload = merge_structured_race_cards(final_structured_payload, jt_retry_payload)
                merged_urls = merge_source_urls(
                    source_urls=merged_urls,
                    annotations=jt_retry_response.get("annotations"),
                )
            except AdminRaceCardJSONError:
                logger.warning("Jockey/trainer gap-fill retry returned malformed JSON — keeping original data")

            remaining_gaps = find_races_with_incomplete_fields(final_structured_payload)
            if remaining_gaps:
                gap_detail = "; ".join(
                    f"Race {rn}: {', '.join(gaps)}" for rn, gaps in sorted(remaining_gaps.items())
                )
                logger.warning(f"Still incomplete after jockey/trainer retry: {gap_detail}")

        if expected_race_numbers and missing_race_numbers:
            missing_labels = ", ".join(str(number) for number in missing_race_numbers)
            logger.warning(f"Partial card accepted — still missing races after retry: {missing_labels}")
        if missing_horses_by_race:
            logger.warning(
                f"Partial card accepted — still missing horses after retry: {_format_missing_horses_by_race(missing_horses_by_race)}"
            )

        normalized_results = normalize_admin_results(
            final_structured_payload,
            race_date=request.race_date,
            track_id=request.track_id,
            llm_model=request.llm_model,
            expected_horses_by_race=expected_horses_by_race,
            source_urls=merged_urls,
            admin_notes=request.admin_notes,
            workflow="admin_openrouter_web_search" if is_web_search_mode else "admin_openrouter_manual",
            analysis_duration_seconds=time.perf_counter() - started_at,
        )

        await session_manager.save_session_results(session_id, normalized_results)
        await session_manager.update_session_status(
            session_id, "completed", 100, "analysis_complete", "Admin race card saved"
        )

        return JSONResponse({
            "session_id": session_id,
            "status": "completed",
            "redirect_url": f"/results/{session_id}",
        })
    except ValueError as exc:
        await session_manager.update_session_status(
            session_id, "failed", 0, "admin_failed", str(exc)
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException as exc:
        await session_manager.update_session_status(
            session_id, "failed", 0, "admin_failed", str(exc.detail)
        )
        raise
    except Exception as exc:
        logger.error(f"Admin race card creation failed: {exc}")
        await session_manager.update_session_status(
            session_id, "failed", 0, "admin_failed", str(exc)
        )
        raise HTTPException(status_code=500, detail=f"Failed to create admin race card: {exc}") from exc


@app.get("/api/admin/sessions")
async def list_admin_sessions(request: Request):
    """List recent admin-created race card sessions for the deep-dive tab."""
    if not _auth_enabled():
        raise HTTPException(status_code=503, detail="Admin access is not configured on the server")
    if not _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin authentication required")

    session_manager = await app_state.ensure_session_manager()
    if not session_manager:
        raise HTTPException(status_code=503, detail="Session manager is not available")

    sessions = await session_manager.get_recent_sessions(20)
    return JSONResponse(sessions)


@app.get("/api/results-json/{session_id}")
async def get_session_results_json(session_id: str, request: Request):
    """Return raw session results JSON — used by the deep-dive tab to enumerate races."""
    if not _auth_enabled():
        raise HTTPException(status_code=503, detail="Admin access is not configured on the server")
    if not _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin authentication required")

    session_manager = await app_state.ensure_session_manager()
    if not session_manager:
        raise HTTPException(status_code=503, detail="Session manager is not available")

    results = await session_manager.get_session_results(session_id)
    if "error" in results:
        raise HTTPException(status_code=404, detail=results["error"])
    return JSONResponse(results)


@app.post("/api/admin/race-deep-dive")
async def admin_race_deep_dive(request: AdminDeepDiveRequest, http_request: Request = None):
    """Deep-dive into one race: search for workouts, recent form, and jockey/trainer stats for every horse."""
    if not _auth_enabled():
        raise HTTPException(status_code=503, detail="Admin access is not configured on the server")
    if http_request is None or not _is_admin(http_request):
        raise HTTPException(status_code=403, detail="Admin authentication required")

    session_manager = await app_state.ensure_session_manager()
    openrouter_client = app_state.ensure_openrouter_client()

    if not session_manager:
        raise HTTPException(status_code=503, detail="Session manager is not available")
    if not openrouter_client or not openrouter_client.api_key:
        raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY is not configured on the server")
    if not extract_json_object:
        raise HTTPException(status_code=503, detail="Admin race-card helpers are unavailable")

    logger.info(
        "🔍 DEEP-DIVE: session=%s | race=%s | date=%s | track=%s",
        request.session_id, request.race_number, request.race_date, request.track_id,
    )

    session_results = await session_manager.get_session_results(request.session_id)
    if "error" in session_results:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_results['error']}")

    race_analyses = session_results.get("race_analyses", [])
    target_race = next(
        (r for r in race_analyses if r.get("race_number") == request.race_number),
        None,
    )
    if not target_race:
        raise HTTPException(
            status_code=404,
            detail=f"Race {request.race_number} not found in session {request.session_id}",
        )

    horses = target_race.get("predictions", [])
    if not horses:
        raise HTTPException(
            status_code=404,
            detail=f"No horses found for Race {request.race_number}",
        )

    # ── Cache look-up ──────────────────────────────────────────────────────────
    if not request.force_refresh:
        cached = await session_manager.get_race_deep_dive(
            request.race_date, request.track_id, request.race_number
        )
        if cached:
            deep_dive_data = cached.get("deep_dive", {})
            cached_urls = cached.get("source_urls", [])
            horses_enriched = len(deep_dive_data.get("horses", []))
            logger.info(
                "🎯 DEEP-DIVE CACHE HIT: race=%s | date=%s | track=%s | horses=%s",
                request.race_number, request.race_date, request.track_id, horses_enriched,
            )
            return JSONResponse({
                "session_id": request.session_id,
                "race_number": request.race_number,
                "horses_enriched": horses_enriched,
                "deep_dive": deep_dive_data,
                "source_urls": cached_urls,
                "from_cache": True,
            })

    horse_lines = []
    for h in horses:
        name = h.get("horse") or h.get("name", "Unknown")
        post = h.get("post_position", "?")
        jockey = h.get("jockey", "")
        trainer = h.get("trainer", "")
        horse_lines.append(f"  - Post {post}: {name} (Jockey: {jockey}, Trainer: {trainer})")

    track_full = SUPPORTED_TRACKS.get(request.track_id, request.track_id)
    track_country = get_track_country(request.track_id)
    intl = track_country != "USA"
    race_info = (
        f"Race {request.race_number} on {request.race_date} at {track_full} ({request.track_id}) | "
        f"Country: {track_country} | "
        f"{target_race.get('race_type', '')} | {target_race.get('distance', '')} | {target_race.get('surface', '')}"
    )

    if intl:
        search_sources = (
            "Search the following sources for data on each horse:\n"
            "  - nar.netkeiba.com (Japanese racing — past results, speed figures, jockey/trainer stats)\n"
            "  - irace.com.sg (international form guides)\n"
            "  - skyracingworld.com (form guides for Japan/Australia)\n"
            "  - tabtouch.com.au / tab.com.au (Australian racing data)\n"
            "  - equibase.com/static/foreign/ (Equibase international entries)\n"
            "Cross-reference multiple sources. Note: Beyer speed figures are NOT available for international races — use local speed ratings or time-based figures instead."
        )
    else:
        search_sources = "Search equibase.com, horseracingnation.com, brisnet.com, and any other authoritative racing data sources."

    prompt = f"""You are a professional horse racing data analyst. Perform a comprehensive deep-dive data collection for the following race.

RACE: {race_info}

HORSES ({len(horses)} starters):
{chr(10).join(horse_lines)}

For EACH horse above, search the web and collect ALL of the following data points:
1. **Recent race results** — Last 5 races: date, track, distance, surface, finish position, speed figure/Beyer, beaten lengths, odds, race type/class
2. **Recent workouts** — Last 4 weeks: date, track, distance, time, rank (e.g. "1/20"), workout type (bullet/handily/breezing)
3. **Jockey stats** — Win % at {track_full}, win % at this distance/surface, last-30-day form (starts-wins-places-shows)
4. **Trainer stats** — Win % at {track_full}, win % at this class/distance, last-30-day form
5. **Form notes** — beaten favorite? class drop/rise? equipment change? medication? current condition?

{search_sources}

Return ONLY a valid JSON object with this exact structure:
{{
  "race_number": {request.race_number},
  "race_date": "{request.race_date}",
  "track_id": "{request.track_id}",
  "horses": [
    {{
      "name": "Horse Name",
      "post_position": 1,
      "jockey": "Jockey Name",
      "trainer": "Trainer Name",
      "recent_results": [
        {{"date": "YYYY-MM-DD", "track": "XX", "distance": "6f", "surface": "Dirt", "finish": 1, "speed_figure": 95, "beaten_lengths": 0.0, "odds": "2-1", "race_type": "CLM"}}
      ],
      "workouts": [
        {{"date": "YYYY-MM-DD", "track": "XX", "distance": "4F", "time": "48.2", "rank": "1/20", "type": "bullet"}}
      ],
      "jockey_stats": {{"track_win_pct": 22, "distance_win_pct": 18, "last_30_days": "12-3-2-1"}},
      "trainer_stats": {{"track_win_pct": 15, "distance_win_pct": 12, "last_30_days": "8-2-1-0"}},
      "form_notes": "Brief sharp condition assessment"
    }}
  ],
  "deep_dive_summary": "Overall race dynamics and standout horses"
}}"""

    try:
        response = await openrouter_client.call_model(
            model="x-ai/grok-4.20-beta",
            task_type="analysis",
            prompt=prompt,
            context={
                "race_date": request.race_date,
                "track_id": request.track_id,
                "race_number": request.race_number,
                "session_id": request.session_id,
            },
            max_tokens=ADMIN_DEEP_DIVE_MAX_TOKENS,
            temperature=0.1,
            plugins=[{"id": "web"}],
            return_metadata=True,
            response_format={"type": "json_object"},
        )

        content = response.get("content", "") if isinstance(response, dict) else ""
        if not content:
            raise HTTPException(status_code=502, detail="Grok returned empty content for deep-dive")

        deep_dive_data = extract_json_object(content)

        enriched_horses = deep_dive_data.get("horses", [])
        for horse_data in enriched_horses:
            horse_name = horse_data.get("name", "")
            if horse_name:
                await session_manager.cache_horse_data(
                    request.session_id,
                    request.race_date,
                    horse_name,
                    {
                        "last3_results": horse_data.get("recent_results", []),
                        "workouts": horse_data.get("workouts", []),
                        "smartpick": {
                            "jockey_stats": horse_data.get("jockey_stats", {}),
                            "trainer_stats": horse_data.get("trainer_stats", {}),
                            "form_notes": horse_data.get("form_notes", ""),
                        },
                        "quality_rating": 0.0,
                        "profile_url": "",
                    },
                )

        annotations = response.get("annotations", []) if isinstance(response, dict) else []
        source_urls = [a.get("url") for a in annotations if isinstance(a, dict) and a.get("url")]

        logger.info(
            "✅ Deep-dive complete | race=%s | horses_enriched=%s | sources=%s",
            request.race_number, len(enriched_horses), len(source_urls),
        )

        # ── Persist result so subsequent requests return from cache ────────────
        await session_manager.save_race_deep_dive(
            request.session_id,
            request.race_date,
            request.track_id,
            request.race_number,
            deep_dive_data,
            source_urls,
        )

        return JSONResponse({
            "session_id": request.session_id,
            "race_number": request.race_number,
            "horses_enriched": len(enriched_horses),
            "deep_dive": deep_dive_data,
            "source_urls": source_urls,
            "from_cache": False,
        })

    except AdminRaceCardJSONError as exc:
        raise HTTPException(status_code=422, detail=f"Deep-dive JSON parse failed: {exc}") from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Deep-dive failed for race {request.race_number}: {exc}")
        raise HTTPException(status_code=500, detail=f"Deep-dive failed: {exc}") from exc


@app.get("/api/status/{session_id}")
async def get_analysis_status(session_id: str):
    """Get current status of analysis session"""
    try:
        session_manager = await app_state.ensure_session_manager()
        if session_manager:
            status = await session_manager.get_session_status(session_id)

            # Add helpful message for interrupted sessions
            if status.get('status') == 'interrupted':
                status['user_message'] = (
                    "This analysis was interrupted by a server restart. "
                    "This can happen during deployments or maintenance. "
                    "Please start a new analysis."
                )

            return JSONResponse(status)
        else:
            # Fallback status response
            return JSONResponse({
                "session_id": session_id,
                "status": "unknown",
                "progress": 0,
                "current_stage": "initializing",
                "message": "Session manager not available"
            })
    except ValueError as e:
        # Session not found - provide helpful error message
        logger.error(f"Session not found: {session_id}")
        raise HTTPException(
            status_code=404,
            detail=f"Session {session_id} not found. It may have expired or been cleaned up."
        )
    except Exception as e:
        logger.error(f"Failed to get status for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cancel/{session_id}")
async def cancel_analysis(session_id: str):
    """Cancel a running analysis session"""
    try:
        # Cancel the background task if it exists
        if session_id in app_state.active_tasks:
            task = app_state.active_tasks[session_id]
            if not task.done():
                task.cancel()
                logger.info(f"Cancelled analysis task for session {session_id}")
            del app_state.active_tasks[session_id]

        # Update session status
        session_manager = await app_state.ensure_session_manager()
        if session_manager:
            await session_manager.update_session_status(
                session_id, "cancelled", 0, "Cancelled", "Analysis cancelled by user"
            )

        return JSONResponse({
            "session_id": session_id,
            "status": "cancelled",
            "message": "Analysis cancelled successfully"
        })
    except Exception as e:
        logger.error(f"Failed to cancel session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/progress/{session_id}", response_class=HTMLResponse)
async def progress_page(request: Request, session_id: str):
    """Progress tracking page with real-time updates"""
    return templates.TemplateResponse(request, "progress.html", {
        "request": request,
        "session_id": session_id,
        "title": "Analysis in Progress"
    })

@app.get("/results/{session_id}", response_class=HTMLResponse)
async def results_page(request: Request, session_id: str):
    """Results display page"""
    try:
        session_manager = await app_state.ensure_session_manager()
        if session_manager:
            results = await session_manager.get_session_results(session_id)
        else:
            results = {"error": "Session manager not available"}
            
        return templates.TemplateResponse(request, "results.html", {
            "request": request,
            "session_id": session_id,
            "results": results,
            "title": "Analysis Results"
        })
    except Exception as e:
        logger.error(f"Failed to load results for session {session_id}: {e}")
        return templates.TemplateResponse(request, "error.html", {
            "request": request,
            "error": str(e),
            "title": "Error Loading Results"
        })

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "session_manager": app_state.session_manager is not None,
            "orchestration_service": app_state.orchestration_service is not None,
            "openrouter_client": app_state.openrouter_client is not None,
            "prediction_engine": app_state.prediction_engine is not None,
            "gradient_boosting_predictor": app_state.gradient_boosting_predictor is not None,
            "kelly_optimizer": app_state.kelly_optimizer is not None
        }
    }


@app.post("/api/admin/auto-curate")
async def auto_curate_card(request: AutoCurateRequest, http_request: Request = None):
    """Use Grok to synthesize the full race card analysis + all deep-dives and curate the entire card."""
    if not _auth_enabled():
        raise HTTPException(status_code=503, detail="Admin access is not configured on the server")
    if http_request is None or not _is_admin(http_request):
        raise HTTPException(status_code=403, detail="Admin authentication required")

    session_manager = await app_state.ensure_session_manager()
    openrouter_client = app_state.ensure_openrouter_client()

    if not session_manager:
        raise HTTPException(status_code=503, detail="Session manager is not available")
    if not openrouter_client or not openrouter_client.api_key:
        raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY is not configured on the server")

    track_full = SUPPORTED_TRACKS.get(request.track_id, request.track_id)

    # ── 1. Fetch full race card session ──────────────────────────────────────
    session_results = await session_manager.get_session_results(request.session_id)
    if "error" in session_results:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_results['error']}")

    race_analyses = session_results.get("race_analyses", [])
    if not race_analyses:
        raise HTTPException(status_code=404, detail="No race analyses found in session")

    # ── 2. For each race, merge card analysis + cached deep-dive ─────────────
    def _build_horse_block(pred: dict, dd_horse: dict) -> str:
        name = pred.get("horse_name") or pred.get("name") or ""
        post = pred.get("post_position", "?")
        jockey = pred.get("jockey", "")
        trainer = pred.get("trainer", "")
        composite = pred.get("composite_rating", "")
        win_prob = pred.get("win_probability", "")
        notes = pred.get("notes", "")
        factors = pred.get("factors") or {}

        form_notes = dd_horse.get("form_notes", "")
        js = dd_horse.get("jockey_stats") or {}
        ts = dd_horse.get("trainer_stats") or {}
        recent = dd_horse.get("recent_results") or []
        workouts = dd_horse.get("workouts") or []

        recent_str = "; ".join(
            f"{r.get('date','')} Fin{r.get('finish','')} Fig{r.get('speed_figure','')}@{r.get('track','')}"
            for r in recent[:4]
        ) or "N/A"
        workout_str = "; ".join(
            f"{w.get('date','')} {w.get('distance','')} {w.get('time','')}({w.get('type','')})"
            for w in workouts[:3]
        ) or "N/A"

        block = f"  Post {post}: {name} | J:{jockey} T:{trainer}\n"
        block += f"  Rating:{composite} WinProb:{win_prob}%"
        if factors:
            block += f" | Spd:{factors.get('speed_rating',0)} Form:{factors.get('form_rating',0)} Cls:{factors.get('class_rating',0)} Wrk:{factors.get('workout_rating',0)}"
        block += "\n"
        if notes:
            block += f"  CardNote: {notes}\n"
        if form_notes:
            block += f"  FormNote: {form_notes}\n"
        if js:
            block += f"  Jockey: Track{js.get('track_win_pct','?')}% Dist{js.get('distance_win_pct','?')}% 30d:{js.get('last_30_days','?')}\n"
        if ts:
            block += f"  Trainer: Track{ts.get('track_win_pct','?')}% Dist{ts.get('distance_win_pct','?')}% 30d:{ts.get('last_30_days','?')}\n"
        block += f"  Recent: {recent_str}\n"
        block += f"  Workouts: {workout_str}\n"
        return block

    race_sections = []
    horse_names_by_race: dict = {}  # race_number -> list of horse names

    for race in sorted(race_analyses, key=lambda r: r.get("race_number", 0)):
        race_num = race.get("race_number", 0)
        cached_dive = await session_manager.get_race_deep_dive(
            request.race_date, request.track_id, race_num
        )
        dd_data = cached_dive.get("deep_dive", {}) if cached_dive else {}
        dd_by_name = {h.get("name", "").lower(): h for h in dd_data.get("horses", [])}

        predictions = race.get("predictions", [])
        horse_names_by_race[race_num] = [
            (p.get("horse_name") or p.get("name") or "") for p in predictions
        ]

        section = (
            f"RACE {race_num} — {race.get('race_type','?')} | "
            f"{race.get('distance','?')} | {race.get('surface','?')}\n"
        )
        if dd_data.get("deep_dive_summary"):
            section += f"DeepDiveSummary: {dd_data['deep_dive_summary']}\n"
        for pred in predictions:
            name = (pred.get("horse_name") or pred.get("name") or "").lower()
            section += _build_horse_block(pred, dd_by_name.get(name, {}))
        race_sections.append(section)

    prompt = f"""You are a professional horse racing handicapper. You have the full race card for {track_full} on {request.race_date} — including the initial AI race card analysis AND deep-dive research (workouts, recent form, jockey/trainer stats) for each race.

Re-analyze the entire card using ALL of this combined information. For every race, identify the three best betting angles and write editorial-quality race notes. Then write an overall card overview.

FULL RACE CARD DATA:
{'='*60}
{chr(10).join(race_sections)}
{'='*60}

For each race return:
- top_pick: the horse name with the highest win probability after re-analysis
- value_play: a horse with strong credentials likely undervalued at the windows
- longshot: a horse with realistic upset potential at big odds
- race_notes: 2-3 sentences of editorial analysis explaining the picks and race shape
- betting_strategy: specific bet types (win, exacta key, trifecta, etc.) with post positions

Also return:
- card_overview: 3-4 sentence overview of the overall card themes, standout races, and key angles for the day

Return ONLY valid JSON:
{{
  "card_overview": "Overall card analysis...",
  "races": [
    {{
      "race_number": 1,
      "top_pick": "Exact Horse Name",
      "value_play": "Exact Horse Name",
      "longshot": "Exact Horse Name",
      "race_notes": "Editorial 2-3 sentence analysis...",
      "betting_strategy": "Win on #X, exacta key X/Y,Z, trifecta..."
    }}
  ]
}}"""

    logger.info(
        "🤖 FULL-CARD AUTO-CURATE: session=%s | track=%s | date=%s | races=%s",
        request.session_id, request.track_id, request.race_date, len(race_analyses),
    )

    # ── 3. Call Grok (no web plugins — data is already in hand) ──────────────
    try:
        response = await openrouter_client.call_model(
            model="x-ai/grok-4.20-beta",
            task_type="analysis",
            prompt=prompt,
            context={"race_date": request.race_date, "track_id": request.track_id},
            max_tokens=4000,
            temperature=0.25,
            return_metadata=True,
            response_format={"type": "json_object"},
        )

        content = response.get("content", "") if isinstance(response, dict) else str(response)
        if not content:
            raise HTTPException(status_code=502, detail="Grok returned empty content for auto-curation")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            import re as _re
            match = _re.search(r'\{.*\}', content, _re.DOTALL)
            if match:
                parsed = json.loads(match.group())
            else:
                raise HTTPException(status_code=502, detail="Could not parse Grok's curation response as JSON")

        races_out = parsed.get("races", [])
        logger.info(
            "✅ FULL-CARD AUTO-CURATE complete | races_returned=%s",
            len(races_out),
        )
        return JSONResponse({
            "card_overview": parsed.get("card_overview", ""),
            "races": races_out,
            "horse_names_by_race": horse_names_by_race,
        })

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Full-card auto-curation failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/admin/curated-card")
async def save_curated_card(request: CuratedCardRequest, http_request: Request = None):
    """Save or update a curated betting card for a race date + track."""
    if not _auth_enabled():
        raise HTTPException(status_code=503, detail="Admin access is not configured on the server")
    if http_request is None or not _is_admin(http_request):
        raise HTTPException(status_code=403, detail="Admin authentication required")

    session_manager = await app_state.ensure_session_manager()
    if not session_manager:
        raise HTTPException(status_code=503, detail="Session manager is not available")

    try:
        card_id = await session_manager.save_curated_card(
            race_date=request.race_date,
            track_id=request.track_id,
            session_id=request.session_id,
            top_pick=request.top_pick,
            value_play=request.value_play,
            longshot=request.longshot,
            admin_notes=request.admin_notes,
            betting_strategy=request.betting_strategy,
            is_published=request.is_published,
            races=request.races,
            card_overview=request.card_overview,
        )
        status = "published" if request.is_published else "saved"
        logger.info(
            "✅ Curated card %s | date=%s | track=%s | id=%s",
            status, request.race_date, request.track_id, card_id,
        )
        return JSONResponse({
            "id": card_id,
            "status": status,
            "race_date": request.race_date,
            "track_id": request.track_id,
            "card_url": f"/card/{request.race_date}/{request.track_id}",
        })
    except Exception as exc:
        logger.error(f"Failed to save curated card: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/curated-cards")
async def list_curated_cards(request: Request):
    """List all curated cards (admin only)."""
    if not _auth_enabled():
        raise HTTPException(status_code=503, detail="Admin access is not configured on the server")
    if not _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin authentication required")

    session_manager = await app_state.ensure_session_manager()
    if not session_manager:
        raise HTTPException(status_code=503, detail="Session manager is not available")

    cards = await session_manager.get_all_curated_cards(limit=50)
    for card in cards:
        card["track_name"] = SUPPORTED_TRACKS.get(card.get("track_id"), card.get("track_id"))
        card["card_url"] = f"/card/{card.get('race_date')}/{card.get('track_id')}"
    return JSONResponse(cards)


@app.get("/card/{race_date}/{track_id}", response_class=HTMLResponse)
async def curated_card_page(request: Request, race_date: str, track_id: str):
    """Public-facing curated betting card page."""
    session_manager = await app_state.ensure_session_manager()
    card = None
    if session_manager:
        card = await session_manager.get_curated_card(race_date, track_id)

    if not card:
        return templates.TemplateResponse(
            request,
            "error.html",
            _template_context(
                request,
                "Card Not Found",
                error=f"No curated card found for {SUPPORTED_TRACKS.get(track_id, track_id)} on {race_date}.",
            ),
            status_code=404,
        )

    track_name = SUPPORTED_TRACKS.get(track_id, track_id)
    return templates.TemplateResponse(
        request,
        "curated_card.html",
        _template_context(
            request,
            f"{track_name} · {race_date} — TrackStarAI Curated Card",
            card=card,
            race_date=race_date,
            track_id=track_id,
            track_name=track_name,
        ),
    )


def _validate_track_id(track_id: str):
    if track_id not in SUPPORTED_TRACKS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid track ID. Supported tracks: {', '.join(SUPPORTED_TRACKS.keys())}",
        )


def _validate_llm_model(llm_model: str):
    if llm_model not in _get_configured_model_ids():
        raise HTTPException(
            status_code=400,
            detail="Invalid LLM model. Use one of the configured OpenRouter models.",
        )


async def _load_dashboard_cards(limit: int = 8) -> List[Dict]:
    if not app_state.session_manager:
        return []

    sessions = await app_state.session_manager.get_recent_sessions(limit=limit)
    completed_sessions = [session for session in sessions if session.get("status") == "completed"]
    results_by_session: Dict[str, Dict] = {}

    if completed_sessions:
        fetched_results = await asyncio.gather(
            *(app_state.session_manager.get_session_results(session["session_id"]) for session in completed_sessions),
            return_exceptions=True,
        )
        for session, results in zip(completed_sessions, fetched_results):
            if isinstance(results, dict):
                results_by_session[session["session_id"]] = results

    dashboard_cards = []
    for session in sessions:
        session_id = session.get("session_id")
        results = results_by_session.get(session_id, {})
        summary = results.get("summary", {}) if isinstance(results, dict) else {}
        best_bet = (summary.get("best_bets") or [None])[0]
        dashboard_cards.append({
            "session_id": session_id,
            "race_date": session.get("race_date"),
            "track_id": session.get("track_id"),
            "track_name": SUPPORTED_TRACKS.get(session.get("track_id"), session.get("track_id")),
            "llm_model": session.get("llm_model"),
            "model_label": _build_model_option(session.get("llm_model") or "").get("label", session.get("llm_model")),
            "status": session.get("status", "unknown"),
            "status_class": STATUS_BADGE_CLASSES.get(session.get("status"), "secondary"),
            "progress": session.get("progress", 0),
            "updated_at": session.get("updated_at"),
            "generated_at": results.get("generated_at") if isinstance(results, dict) else None,
            "total_races": summary.get("total_races", 0),
            "total_horses": summary.get("total_horses", 0),
            "best_bet": best_bet,
        })

    return dashboard_cards


async def _safe_load_dashboard_cards(limit: int = 8) -> List[Dict]:
    try:
        return await asyncio.wait_for(_load_dashboard_cards(limit=limit), timeout=2.0)
    except asyncio.TimeoutError:
        logger.warning("Dashboard card loading timed out; serving landing page without cards")
    except Exception as e:
        logger.warning(f"Dashboard card loading failed; serving landing page without cards: {e}")
    return []


def _build_admin_structuring_prompt(
    request: AdminRaceCardRequest,
    *,
    expected_race_numbers: Optional[List[int]] = None,
    missing_race_numbers: Optional[List[int]] = None,
    expected_horses_by_race: Optional[Dict[int, List[str]]] = None,
    missing_horses_by_race: Optional[Dict[int, List[str]]] = None,
    official_card_url: Optional[str] = None,
    per_race_urls: Optional[Dict[int, Dict[str, str]]] = None,
    compact_response: bool = False,
) -> str:
    track_country = get_track_country(request.track_id)
    intl = track_country != "USA"

    if request.source_mode != "web_search":
        source_strategy = "Use only the supplied source material. Do not rely on outside knowledge or browse the web."
    elif intl:
        source_strategy = (
            "Use web search before answering. "
            "This is an INTERNATIONAL track — Equibase SmartPick pages do NOT exist for this region. "
            "Your PRIMARY data sources are the Equibase foreign entry pages listed below. "
            "ALSO search these supplementary sources for speed figures, form, and statistics:\n"
            "  - nar.netkeiba.com (Japanese racing speed/stats — use race_id format matching the track and date)\n"
            "  - irace.com.sg (international form guides and express form PDFs)\n"
            "  - skyracingworld.com (form guides for Japan/Australia)\n"
            "  - tabtouch.com.au / tab.com.au (Australian racing data)\n"
            "Cross-reference multiple sources to build the most complete field possible. "
            "Do not skip later races."
        )
    else:
        source_strategy = (
            "Use web search before answering. "
            "Your PRIMARY data sources are the Equibase SmartPick pages listed below — you MUST search the SmartPick URL for EVERY race "
            "(not just the first few) to get the full field, post positions, jockeys, trainers, morning line odds, and SmartPick rankings. "
            "Do not skip later races. Cross-reference with the Equibase entry pages and other high-confidence racing sources."
        )
    expected_race_numbers = expected_race_numbers or []
    missing_race_numbers = missing_race_numbers or []
    expected_horses_by_race = expected_horses_by_race or {}
    missing_horses_by_race = missing_horses_by_race or {}
    per_race_urls = per_race_urls or {}

    if missing_race_numbers or missing_horses_by_race:
        retry_requirements: List[str] = ["This is a retry."]
        if missing_race_numbers:
            retry_requirements.append(
                f"Return race analyses ONLY for these missing races: {', '.join(str(number) for number in missing_race_numbers)}."
            )
        if missing_horses_by_race:
            retry_requirements.append(
                "For these incomplete races, return the FULL field in strongest-to-weakest order: "
                f"{', '.join(str(number) for number in sorted(missing_horses_by_race))}."
            )
            retry_requirements.append(
                f"Missing horses on retry: {_format_missing_horses_by_race(missing_horses_by_race)}."
            )
        retry_requirements.append("Do not repeat races that are already complete.")
        discovery_requirements = " ".join(retry_requirements)
    elif expected_race_numbers:
        discovery_requirements = (
            f"The official card expects exactly these races: {', '.join(str(number) for number in expected_race_numbers)}. "
            "Return every one of those races exactly once."
        )
    elif request.source_mode == "web_search":
        discovery_requirements = "Include every race you can identify for the selected track and date."
    else:
        discovery_requirements = "Include every race you can identify from the supplied material."

    official_url_line = f"Official card overview URL: {official_card_url}" if official_card_url else ""
    official_field_summary = _format_expected_field_summary(expected_horses_by_race)

    # Build per-race URL reference block for the prompt
    smartpick_url_block = ""
    if per_race_urls:
        url_lines = []
        for race_number in sorted(per_race_urls):
            urls = per_race_urls[race_number]
            if urls.get("smartpick"):
                url_lines.append(f"  Race {race_number}: SmartPick={urls['smartpick']}  Entry={urls['entry']}")
            else:
                url_lines.append(f"  Race {race_number}: Entry={urls['entry']}")
        label = "Equibase URLs by race (search these for accurate data):"
        smartpick_url_block = label + "\n" + "\n".join(url_lines)

    compact_retry_line = (
        "This is a compact retry because the previous answer was malformed or truncated JSON. "
        "Keep the payload lean so the full card fits in one valid JSON object."
        if compact_response
        else ""
    )
    response_shape = (
        """{
  "card_overview": "short summary",
  "race_analyses": [
    {
      "race_number": 1,
      "race_type": "Allowance Optional Claiming",
      "distance": "6f",
      "surface": "Dirt",
      "predictions": [
        {
          "horse_name": "Horse Name",
          "post_position": 1,
          "jockey": "Jockey Name",
          "trainer": "Trainer Name",
          "composite_rating": 88.5
        }
      ]
    }
  ]
}"""
        if compact_response
        else """{
  "card_overview": "short summary",
  "race_analyses": [
    {
      "race_number": 1,
      "race_type": "Allowance Optional Claiming",
      "distance": "6f",
      "surface": "Dirt",
      "predictions": [
        {
          "horse_name": "Horse Name",
          "post_position": 1,
          "jockey": "Jockey Name",
          "trainer": "Trainer Name",
          "morning_line_odds": "5-1",
          "composite_rating": 88.5,
          "factors": {
            "speed_rating": 88,
            "form_rating": 84,
            "class_rating": 82,
            "workout_rating": 80
          },
          "notes": "brief grounded note"
        }
      ],
      "exotic_suggestions": {"exacta": "1-4", "trifecta": "1-4-6"}
    }
  ]
}"""
    )
    compact_rules = (
        "- Compact retry mode: omit `factors` and `exotic_suggestions`.\n"
        "- Omit per-horse `notes` unless absolutely necessary.\n"
        if compact_response
        else (
            "- If evidence is limited, still rank the full field strongest to weakest and keep notes concise about uncertainty.\n"
            "- Keep notes concise — one sentence max per horse.\n"
        )
    )

    # Data source rules differ for USA vs international
    if intl:
        data_source_rules = (
            "- Use the Equibase foreign entry pages as your primary source for the field, post positions, jockeys, and trainers.\n"
            "- ALSO search nar.netkeiba.com, irace.com.sg, skyracingworld.com, tabtouch.com.au, and tab.com.au for supplementary speed figures, form data, and statistics.\n"
            "- **Jockey and trainer are MANDATORY for every horse.** Search multiple sources to find this data. Never use \"N/A\", \"Unknown\", or leave them blank.\n"
            "- Include `morning_line_odds` for each horse if available from any source."
        )
    else:
        data_source_rules = (
            "- Use the Equibase SmartPick data as your primary source for post positions, jockeys, trainers, and morning line odds.\n"
            "- **Jockey and trainer are MANDATORY for every horse.** Search the SmartPick page for EACH race to get this data. Never use \"N/A\", \"Unknown\", or leave them blank.\n"
            "- Include `morning_line_odds` for each horse if available from the SmartPick or entry pages."
        )

    return f"""
You are structuring a horse racing card for internal display.

Track: {SUPPORTED_TRACKS[request.track_id]} ({request.track_id})
Country: {track_country}
Race date: {request.race_date}
Source mode: {request.source_mode}
{source_strategy}
{official_url_line}
{smartpick_url_block}
{official_field_summary}
{compact_retry_line}

Return ONLY valid JSON with this shape:
{response_shape}

Rules:
- Do not wrap the JSON in markdown fences.
- {discovery_requirements}
- Prioritize covering every race on the card over exhaustive writeups for a single race.
- Return a ranked prediction for EVERY horse in every returned race. Never truncate to only the top 3-5 horses.
- If official horse names are provided, include every listed horse exactly once in that race.
- Order each race's predictions strongest to weakest.
{data_source_rules}
- Use only grounded details; leave uncertain text blank instead of inventing facts — but jockey and trainer must always be populated.
- `composite_rating` must be numeric on a 0-100 scale.
{compact_rules}""".strip()


def _should_retry_admin_json_with_compact_prompt(
    request: AdminRaceCardRequest,
    model_name: Optional[str],
) -> bool:
    if request.source_mode != "web_search":
        return False

    base_model = str(model_name or request.llm_model or "").split(":", 1)[0].lower()
    return any(base_model.startswith(prefix) for prefix in ADMIN_COMPACT_JSON_RETRY_MODEL_PREFIXES)


def _build_admin_json_http_exception(
    request: AdminRaceCardRequest,
    openrouter_response: object,
    *,
    phase_label: str,
    exc: AdminRaceCardJSONError,
) -> HTTPException:
    model_name = (
        str(openrouter_response.get("model") or request.llm_model)
        if isinstance(openrouter_response, dict)
        else request.llm_model
    )
    return HTTPException(
        status_code=422,
        detail=(
            f"OpenRouter returned malformed structured data while {phase_label} using {model_name}. "
            f"{exc.public_message} Try again or choose a model with stronger JSON support."
        ),
    )


def _build_admin_structuring_context(
    request: AdminRaceCardRequest,
    source_text: str,
    *,
    expected_race_numbers: Optional[List[int]] = None,
    missing_race_numbers: Optional[List[int]] = None,
    expected_horses_by_race: Optional[Dict[int, List[str]]] = None,
    missing_horses_by_race: Optional[Dict[int, List[str]]] = None,
    official_card_url: Optional[str] = None,
    per_race_urls: Optional[Dict[int, Dict[str, str]]] = None,
) -> Dict[str, object]:
    context: Dict[str, object] = {
        "race_date": request.race_date,
        "track_id": request.track_id,
        "track_name": SUPPORTED_TRACKS[request.track_id],
        "source_mode": request.source_mode,
        "source_urls": request.source_urls,
        "admin_notes": request.admin_notes,
    }
    if expected_race_numbers:
        context["expected_race_numbers"] = expected_race_numbers
    if missing_race_numbers:
        context["missing_race_numbers"] = missing_race_numbers
    if expected_horses_by_race:
        context["expected_horses_by_race"] = expected_horses_by_race
    if missing_horses_by_race:
        context["missing_horses_by_race"] = missing_horses_by_race
    if official_card_url:
        context["official_card_url"] = official_card_url
    if per_race_urls:
        context["per_race_urls"] = per_race_urls
    if source_text:
        context["source_text"] = source_text
    return context


def _format_expected_field_summary(expected_horses_by_race: Dict[int, List[str]]) -> str:
    if not expected_horses_by_race:
        return ""

    race_summaries = []
    for race_number in sorted(expected_horses_by_race):
        horse_names = expected_horses_by_race[race_number]
        if horse_names:
            race_summaries.append(f"Race {race_number} ({len(horse_names)}): {', '.join(horse_names)}")
    if not race_summaries:
        return ""
    return "Official horse fields by race: " + " | ".join(race_summaries)


def _filter_missing_horses_by_race(
    missing_horses_by_race: Dict[int, List[str]],
    *,
    excluded_race_numbers: Optional[List[int]] = None,
) -> Dict[int, List[str]]:
    excluded = set(excluded_race_numbers or [])
    return {
        race_number: horse_names
        for race_number, horse_names in sorted(missing_horses_by_race.items())
        if horse_names and race_number not in excluded
    }


def _format_missing_horses_by_race(missing_horses_by_race: Dict[int, List[str]]) -> str:
    return "; ".join(
        f"Race {race_number}: {', '.join(horse_names)}"
        for race_number, horse_names in sorted(missing_horses_by_race.items())
        if horse_names
    )


def _build_jockey_trainer_retry_prompt(
    request: AdminRaceCardRequest,
    *,
    incomplete_field_races: Dict[int, List[str]],
    per_race_urls: Optional[Dict[int, Dict[str, str]]] = None,
) -> str:
    """Build a targeted prompt to fill in missing jockey/trainer data for specific races."""
    per_race_urls = per_race_urls or {}

    gap_lines: List[str] = []
    for race_number in sorted(incomplete_field_races):
        gaps = incomplete_field_races[race_number]
        gap_lines.append(f"  Race {race_number}: {'; '.join(gaps)}")

    track_country = get_track_country(request.track_id)
    intl = track_country != "USA"

    url_lines: List[str] = []
    for race_number in sorted(per_race_urls):
        urls = per_race_urls[race_number]
        if urls.get("smartpick"):
            url_lines.append(f"  Race {race_number}: SmartPick={urls['smartpick']}  Entry={urls['entry']}")
        else:
            url_lines.append(f"  Race {race_number}: Entry={urls['entry']}")

    url_block = (
        "\nSearch these Equibase URLs for the missing data:\n" + "\n".join(url_lines)
        if url_lines else ""
    )

    if intl:
        search_instruction = (
            "Use web search before answering. This is an INTERNATIONAL track — SmartPick pages do NOT exist. "
            "Search the Equibase foreign entry pages listed below, AND also search nar.netkeiba.com, "
            "irace.com.sg, skyracingworld.com, tabtouch.com.au for jockey/trainer data."
        )
    else:
        search_instruction = "Use web search before answering. Search the Equibase SmartPick and entry pages for each race listed below."

    return f"""
You are filling in missing jockey and trainer data for a horse racing card.

Track: {SUPPORTED_TRACKS[request.track_id]} ({request.track_id})
Country: {track_country}
Race date: {request.race_date}

{search_instruction}
{url_block}

The following races have horses with missing jockey and/or trainer names:
{chr(10).join(gap_lines)}

Return ONLY valid JSON with this shape:
{{
  "race_analyses": [
    {{
      "race_number": 7,
      "predictions": [
        {{
          "horse_name": "Horse Name",
          "jockey": "Jockey Name",
          "trainer": "Trainer Name"
        }}
      ]
    }}
  ]
}}

Rules:
- Do not wrap the JSON in markdown fences.
- ONLY return the races listed above — do not repeat already-complete races.
- Include EVERY horse in each listed race, with the correct jockey and trainer from the SmartPick or entry page.
- Jockey and trainer are MANDATORY — never use "N/A", "Unknown", or leave them blank.
- If a horse is scratched, omit it entirely.
""".strip()


@app.post("/api/validate")
async def run_validation():
    """Run validation framework to test prediction accuracy"""
    try:
        orchestration_service = await app_state.ensure_orchestration_service()
        if not orchestration_service or not orchestration_service.ensure_validation_framework():
            raise HTTPException(status_code=503, detail="Validation framework not available")

        # Run backtest validation
        validation_result = orchestration_service.validation_framework.run_backtest(
            app_state.prediction_engine
        )

        # Generate comprehensive report
        validation_report = orchestration_service.validation_framework.generate_validation_report(
            validation_result
        )

        return {
            "status": "success",
            "validation_report": validation_report,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")

# Background task functions
async def run_analysis_pipeline(session_id: str, date: str, llm_model: str, track_id: str):
    """Background task to run the complete analysis pipeline via OrchestrationService.

    Previous implementation used the legacy ``run_playwright_full_card.main()``
    which bypasses OpenRouter entirely.  This version routes through
    ``OrchestrationService.analyze_race_card`` so the user-selected LLM model
    and AI services are actually used.
    """
    try:
        logger.info(
            "🚀 ANALYZE PIPELINE START | session=%s | date=%s | track=%s | llm_model=%s",
            session_id, date, track_id, llm_model,
        )

        # Check for cancellation before starting
        if session_id not in app_state.active_tasks:
            logger.info(f"Session {session_id} was cancelled before starting")
            return

        # Ensure orchestration service is ready (creates OpenRouterClient etc.)
        orchestration_service = await app_state.ensure_orchestration_service()
        if not orchestration_service:
            raise RuntimeError(
                "OrchestrationService could not be initialized. "
                "Check session manager and config availability."
            )

        # Delegate to the model-aware orchestration pipeline
        results = await orchestration_service.analyze_race_card(
            session_id=session_id,
            race_date=date,
            track_id=track_id,
            llm_model=llm_model,
        )

        logger.info(
            "✅ ANALYZE PIPELINE COMPLETE | session=%s | races=%d | llm_model=%s | "
            "ai_services=%s",
            session_id,
            results.get("total_races", 0),
            llm_model,
            results.get("ai_services_used", {}),
        )

    except asyncio.CancelledError:
        logger.info(f"Analysis pipeline cancelled for session {session_id}")
        if app_state.session_manager:
            await app_state.session_manager.update_session_status(
                session_id, "cancelled", 0, "Cancelled", "Analysis cancelled by user"
            )
        raise  # Re-raise to properly cancel the task

    except Exception as e:
        logger.error(f"Critical error in analysis pipeline for session {session_id}: {e}")
        if app_state.session_manager:
            try:
                await app_state.session_manager.update_session_status(
                    session_id, "failed", 0, "Analysis failed", str(e)
                )
            except Exception:
                pass

    finally:
        # Remove task from active tasks
        if session_id in app_state.active_tasks:
            del app_state.active_tasks[session_id]
            logger.info(f"Cleaned up task for session {session_id}")

# Application lifecycle events
@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    logger.info(f"Starting {BRAND_NAME}")
    await app_state.initialize()
    logger.info("Application startup complete")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown"""
    logger.info(f"Shutting down {BRAND_NAME}")

    # Cancel all active tasks
    for session_id, task in list(app_state.active_tasks.items()):
        if not task.done():
            logger.info(f"Cancelling active task for session {session_id}")
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app_state.active_tasks.clear()
    logger.info("All active tasks cancelled")
    # Add cleanup logic here
    logger.info("Application shutdown complete")

# Development server
if __name__ == "__main__":
    # Create required directories
    os.makedirs("static", exist_ok=True)
    os.makedirs("templates", exist_ok=True)
    os.makedirs("logs", exist_ok=True)

    # Get port from environment (Render.com uses $PORT)
    port = int(os.environ.get("PORT", 8000))
    environment = os.environ.get("ENVIRONMENT", "development")

    # Run development/production server
    if environment == "production":
        # For production, we'll use Gunicorn (started by start.sh)
        # This is just a fallback
        uvicorn.run(
            "app:app",
            host="0.0.0.0",
            port=port,
            reload=False,
            log_level=os.environ.get("LOG_LEVEL", "info").lower(),
            workers=1
        )
    else:
        # Development mode
        uvicorn.run(
            "app:app",
            host="0.0.0.0",
            port=port,
            reload=bool(os.environ.get("RELOAD", True)),
            log_level=os.environ.get("LOG_LEVEL", "info").lower()
        )
