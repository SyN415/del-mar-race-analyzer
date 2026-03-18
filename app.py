#!/usr/bin/env python3
"""
Del Mar Race Analysis Application
Main FastAPI application entry point

Transforms existing horse racing analysis tools into a unified web application
with AI-powered enhancements and professional user interface.
"""

import asyncio
import hashlib
import hmac
import logging
import os
import secrets
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Literal, Optional

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
        build_equibase_card_overview_url,
        extract_json_object,
        fetch_equibase_expected_horses_by_race,
        fetch_equibase_expected_race_numbers,
        find_missing_horses_by_race,
        find_missing_race_numbers,
        merge_source_urls,
        merge_structured_race_cards,
        normalize_admin_results,
    )
except ImportError as e:
    print(f"Some services not available: {e}")
    SessionManager = None
    OpenRouterClient = None
    build_equibase_card_overview_url = None
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

# Initialize FastAPI app
app = FastAPI(
    title="Del Mar Race Analyzer",
    description="AI-Powered Multi-Track Horse Racing Scraper, Analyzer & Prediction Platform",
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
AUTH_COOKIE_NAME = "delmar_auth"
_AUTH_SECRET: str | None = None


def _get_auth_secret() -> str:
    """Return the auth secret, falling back to a per-process random value."""
    global _AUTH_SECRET
    if _AUTH_SECRET is None:
        _AUTH_SECRET = (
            app_state.config.web.auth_secret
            or os.getenv("DELMAR_AUTH_SECRET")
            or secrets.token_hex(32)
        )
    return _AUTH_SECRET


def _get_admin_password() -> str | None:
    return (
        app_state.config.web.admin_password
        or os.getenv("DELMAR_ADMIN_PASSWORD")
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
    """Auth is active only when an admin password is configured."""
    return bool(_get_admin_password())


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


def _get_ai_config():
    return getattr(app_state.config, "ai", None)


def _get_configured_model_ids() -> List[str]:
    ai_config = _get_ai_config()
    configured_models = getattr(ai_config, "available_models", None)
    if isinstance(configured_models, list) and configured_models:
        valid_models = [model_id for model_id in configured_models if model_id in MODEL_CATALOG]
        if valid_models:
            return valid_models
    return list(MODEL_CATALOG.keys())


def _get_default_model(fallback: str) -> str:
    ai_config = _get_ai_config()
    configured_default = getattr(ai_config, "default_model", None)
    available_models = _get_configured_model_ids()
    if configured_default in available_models:
        return configured_default
    if fallback in available_models:
        return fallback
    return available_models[0]


# Supported tracks
SUPPORTED_TRACKS = {
    "DMR": "Del Mar",
    "SA": "Santa Anita"
}

MODEL_OPTIONS = [MODEL_CATALOG[model_id] for model_id in MODEL_CATALOG]
MODEL_LOOKUP = MODEL_CATALOG
DEFAULT_LLM_MODEL = "x-ai/grok-4.20-beta"
DEFAULT_ADMIN_LLM_MODEL = "google/gemini-3.1-flash-lite-preview"
ADMIN_WEB_SEARCH_INITIAL_MAX_TOKENS = 3500
ADMIN_WEB_SEARCH_RETRY_MAX_TOKENS = 2200
ADMIN_MANUAL_MAX_TOKENS = 2500
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
    """Public dashboard for recent race cards."""
    dashboard_cards = await _safe_load_dashboard_cards(limit=8)
    role = _get_current_role(request)
    return templates.TemplateResponse("landing.html", {
        "request": request,
        "title": "Del Mar Race Analyzer",
        "dashboard_cards": dashboard_cards,
        "card_count": len(dashboard_cards),
        "completed_count": len([card for card in dashboard_cards if card["status"] == "completed"]),
        "openrouter_configured": bool(app_state.ensure_openrouter_client() and app_state.openrouter_client.api_key),
        "auth_enabled": _auth_enabled(),
        "user_role": role,
    })


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page for admin access."""
    if not _auth_enabled():
        return RedirectResponse("/admin", status_code=302)
    if _is_admin(request):
        return RedirectResponse("/admin", status_code=302)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "title": "Sign In",
        "error": None,
    })


@app.post("/login")
async def login_submit(request: Request):
    """Handle login form submission."""
    form = await request.form()
    password = form.get("password", "")
    admin_pw = _get_admin_password()

    if not admin_pw:
        return RedirectResponse("/admin", status_code=302)

    if hmac.compare_digest(password, admin_pw):
        response = RedirectResponse("/admin", status_code=302)
        response.set_cookie(
            AUTH_COOKIE_NAME,
            _sign_value("admin"),
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 24,  # 24 hours
        )
        return response

    return templates.TemplateResponse("login.html", {
        "request": request,
        "title": "Sign In",
        "error": "Invalid password. Please try again.",
    })


@app.get("/logout")
async def logout(request: Request):
    """Clear auth cookie and redirect home."""
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie(AUTH_COOKIE_NAME)
    return response


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    """Admin workflow for saving structured race cards with OpenRouter."""
    if _auth_enabled() and not _is_admin(request):
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "title": "Admin Race Card Workflow",
        "model_options": [MODEL_CATALOG[model_id] for model_id in _get_configured_model_ids()],
        "default_model": _get_default_model(DEFAULT_ADMIN_LLM_MODEL),
        "available_tracks": [{"id": track_id, "name": track_name} for track_id, track_name in SUPPORTED_TRACKS.items()],
        "default_date": datetime.now().strftime("%Y-%m-%d"),
        "openrouter_configured": bool(app_state.ensure_openrouter_client() and app_state.openrouter_client.api_key),
        "auth_enabled": _auth_enabled(),
        "user_role": _get_current_role(request),
    })

@app.post("/api/analyze")
async def start_analysis(request: AnalysisRequest, background_tasks: BackgroundTasks):
    """Start race analysis for specified date and track"""
    try:
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
    if _auth_enabled() and (http_request is None or not _is_admin(http_request)):
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

        return extract_json_object(openrouter_response.get("content", ""))

    try:
        is_web_search_mode = request.source_mode == "web_search"
        official_card_url = (
            build_equibase_card_overview_url(request.track_id, request.race_date)
            if is_web_search_mode
            else None
        )
        expected_horses_by_race = (
            fetch_equibase_expected_horses_by_race(request.track_id, request.race_date)
            if is_web_search_mode
            else {}
        )
        expected_race_numbers = (
            fetch_equibase_expected_race_numbers(request.track_id, request.race_date)
            if is_web_search_mode
            else []
        )
        if expected_horses_by_race and not expected_race_numbers:
            expected_race_numbers = sorted(expected_horses_by_race)
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
            ),
            context=_build_admin_structuring_context(
                request,
                source_text,
                expected_race_numbers=expected_race_numbers,
                expected_horses_by_race=expected_horses_by_race,
                official_card_url=official_card_url,
            ),
            max_tokens=(
                ADMIN_WEB_SEARCH_INITIAL_MAX_TOKENS
                if is_web_search_mode
                else ADMIN_MANUAL_MAX_TOKENS
            ),
            temperature=0.2,
            plugins=[{"id": "web"}] if is_web_search_mode else None,
            return_metadata=True,
        )
        structured_payload = extract_admin_openrouter_payload(
            openrouter_response,
            phase_label="structuring the admin race card",
        )
        merged_urls = merge_source_urls(
            source_urls=request.source_urls + ([official_card_url] if official_card_url else []),
            annotations=openrouter_response.get("annotations"),
        )

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
                ),
                context=_build_admin_structuring_context(
                    request,
                    source_text,
                    expected_race_numbers=expected_race_numbers,
                    missing_race_numbers=missing_race_numbers,
                    expected_horses_by_race=expected_horses_by_race,
                    missing_horses_by_race=missing_horses_by_race,
                    official_card_url=official_card_url,
                ),
                max_tokens=ADMIN_WEB_SEARCH_RETRY_MAX_TOKENS,
                temperature=0.2,
                plugins=[{"id": "web"}],
                return_metadata=True,
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

        if expected_race_numbers and missing_race_numbers:
            missing_labels = ", ".join(str(number) for number in missing_race_numbers)
            raise ValueError(f"Model response was incomplete. Missing races: {missing_labels}")
        if missing_horses_by_race:
            raise ValueError(
                f"Model response was incomplete. Missing horses: {_format_missing_horses_by_race(missing_horses_by_race)}"
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
    return templates.TemplateResponse("progress.html", {
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
            
        return templates.TemplateResponse("results.html", {
            "request": request,
            "session_id": session_id,
            "results": results,
            "title": "Analysis Results"
        })
    except Exception as e:
        logger.error(f"Failed to load results for session {session_id}: {e}")
        return templates.TemplateResponse("error.html", {
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
            "model_label": MODEL_LOOKUP.get(session.get("llm_model"), {}).get("label", session.get("llm_model")),
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
) -> str:
    source_strategy = (
        "Use web search before answering. Prefer official or high-confidence racing sources for the selected card, and cross-check fields when needed."
        if request.source_mode == "web_search"
        else "Use only the supplied source material. Do not rely on outside knowledge or browse the web."
    )
    expected_race_numbers = expected_race_numbers or []
    missing_race_numbers = missing_race_numbers or []
    expected_horses_by_race = expected_horses_by_race or {}
    missing_horses_by_race = missing_horses_by_race or {}

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

    official_url_line = f"Official card URL: {official_card_url}" if official_card_url else ""
    official_field_summary = _format_expected_field_summary(expected_horses_by_race)

    return f"""
You are structuring a horse racing card for internal display.

Track: {SUPPORTED_TRACKS[request.track_id]} ({request.track_id})
Race date: {request.race_date}
Source mode: {request.source_mode}
{source_strategy}
{official_url_line}
{official_field_summary}

Return ONLY valid JSON with this shape:
{{
  "card_overview": "short summary",
  "race_analyses": [
    {{
      "race_number": 1,
      "race_type": "Allowance Optional Claiming",
      "distance": "6f",
      "surface": "Dirt",
      "predictions": [
        {{
          "horse_name": "Horse Name",
          "post_position": 1,
          "jockey": "Jockey Name",
          "trainer": "Trainer Name",
          "composite_rating": 88.5,
          "factors": {{
            "speed_rating": 88,
            "form_rating": 84,
            "class_rating": 82,
            "workout_rating": 80
          }},
          "notes": "brief grounded note"
        }}
      ],
      "exotic_suggestions": {{"exacta": "1-4", "trifecta": "1-4-6"}}
    }}
  ]
}}

Rules:
- Do not wrap the JSON in markdown fences.
- {discovery_requirements}
- Prioritize covering every race on the card over exhaustive writeups for a single race.
- Return a ranked prediction for EVERY horse in every returned race. Never truncate to only the top 3-5 horses.
- If official horse names are provided, include every listed horse exactly once in that race.
- Order each race's predictions strongest to weakest.
- Use only grounded details; leave uncertain text blank instead of inventing facts.
- `composite_rating` must be numeric on a 0-100 scale.
- If evidence is limited, still rank the full field strongest to weakest and keep notes concise about uncertainty.
- Keep notes concise.
""".strip()


def _build_admin_structuring_context(
    request: AdminRaceCardRequest,
    source_text: str,
    *,
    expected_race_numbers: Optional[List[int]] = None,
    missing_race_numbers: Optional[List[int]] = None,
    expected_horses_by_race: Optional[Dict[int, List[str]]] = None,
    missing_horses_by_race: Optional[Dict[int, List[str]]] = None,
    official_card_url: Optional[str] = None,
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
    """Background task to run the complete analysis pipeline"""
    try:
        logger.info(f"Starting analysis pipeline for session {session_id}")

        # Check for cancellation before starting
        if session_id not in app_state.active_tasks:
            logger.info(f"Session {session_id} was cancelled before starting")
            return
        
        # Update session status
        if app_state.session_manager:
            await app_state.session_manager.update_session_status(
                session_id, "running", 10, "Initializing scraping", "Setting up scrapers..."
            )
        
        # Step 1: Initialize scrapers
        playwright_scraper = None
        smartpick_scraper = None
        
        try:
            # Get session details to set environment variables
            session_details = None
            race_date = date
            if app_state.session_manager:
                session_details = await app_state.session_manager.get_session_status(session_id)

            # Set environment variables for the pipeline
            if session_details and 'race_date' in session_details:
                race_date = session_details['race_date']
            os.environ['RACE_DATE_STR'] = race_date
            logger.info(f"Set RACE_DATE_STR to {race_date}")

            # Set track ID environment variable
            if track_id:
                os.environ['TRACK_ID'] = track_id
                logger.info(f"Set TRACK_ID to {track_id}")

            # This will be replaced with proper orchestration service
            # For now, use existing pipeline logic
            from run_playwright_full_card import main as run_existing_pipeline

            # Update status
            if app_state.session_manager:
                await app_state.session_manager.update_session_status(
                    session_id, "running", 50, "Running analysis", "Executing analysis pipeline..."
                )

            # Run existing pipeline (temporary integration)
            results = await run_existing_pipeline()

            if not isinstance(results, dict):
                raise RuntimeError("Analysis pipeline returned an invalid result payload")
            if results.get("error"):
                raise RuntimeError(results["error"])
            if not results.get("race_analyses"):
                raise RuntimeError("Analysis pipeline completed without race analyses")

            results.setdefault("race_date", race_date)
            results.setdefault("track_id", track_id)
            
            # Update final status
            if app_state.session_manager:
                await app_state.session_manager.update_session_status(
                    session_id, "completed", 100, "Analysis complete", "Results ready"
                )
                await app_state.session_manager.save_session_results(session_id, results)
            
            logger.info(f"Analysis pipeline completed for session {session_id}")
            
        except Exception as e:
            logger.error(f"Analysis pipeline failed for session {session_id}: {e}")
            if app_state.session_manager:
                await app_state.session_manager.update_session_status(
                    session_id, "failed", 0, "Analysis failed", str(e)
                )
        finally:
            # Cleanup resources
            if playwright_scraper:
                await playwright_scraper.close()
            if smartpick_scraper:
                smartpick_scraper.close()

    except asyncio.CancelledError:
        logger.info(f"Analysis pipeline cancelled for session {session_id}")
        if app_state.session_manager:
            await app_state.session_manager.update_session_status(
                session_id, "cancelled", 0, "Cancelled", "Analysis cancelled by user"
            )
        raise  # Re-raise to properly cancel the task

    except Exception as e:
        logger.error(f"Critical error in analysis pipeline for session {session_id}: {e}")

    finally:
        # Remove task from active tasks
        if session_id in app_state.active_tasks:
            del app_state.active_tasks[session_id]
            logger.info(f"Cleaned up task for session {session_id}")

# Application lifecycle events
@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    logger.info("Starting Del Mar Race Analysis Application")
    await app_state.initialize()
    logger.info("Application startup complete")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown"""
    logger.info("Shutting down Del Mar Race Analysis Application")

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
