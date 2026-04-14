#!/usr/bin/env python3
"""
TrackStarAI horse racing intelligence application.

Main FastAPI application entry point for the branded web experience,
protected admin workflow, and AI-assisted race-card analysis pipeline.
"""

import asyncio
import copy
import hashlib
import json
import hmac
import logging
import os
import re
import secrets
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from xml.sax.saxutils import escape as xml_escape

try:
    import uvicorn
except ImportError:  # pragma: no cover - optional unless running app.py directly
    uvicorn = None
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
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
    from services.ai_analysis_enhancer import AIAnalysisEnhancer
    from services.race_card_admin import (
        AdminRaceCardJSONError,
        _EMPTY_FIELD_VALUES,
        build_equibase_card_overview_url,
        build_equibase_race_urls,
        extract_json_object,
        fetch_equibase_all_data,
        fetch_equibase_entry_details_by_race,
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
    AIAnalysisEnhancer = None
    AdminRaceCardJSONError = ValueError
    _EMPTY_FIELD_VALUES: set = set()
    build_equibase_card_overview_url = None
    build_equibase_race_urls = None
    extract_json_object = None
    fetch_equibase_all_data = None
    fetch_equibase_entry_details_by_race = None
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


def _is_automation_token_valid(request: Request) -> bool:
    """Check if the request carries a valid automation bearer token."""
    token = os.getenv("TRACKSTAR_AUTOMATION_TOKEN", "")
    if not token:
        return False
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return False
    return hmac.compare_digest(auth_header[7:], token)


def _is_admin(request: Request) -> bool:
    return _get_current_role(request) == "admin" or _is_automation_token_valid(request)


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


def _normalize_public_text(value: Any, max_length: int = 180) -> str:
    """Collapse whitespace and trim text to a sensible SEO-safe length."""
    collapsed = " ".join(str(value or "").split())
    if len(collapsed) <= max_length:
        return collapsed
    trimmed = collapsed[: max_length - 1].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    return f"{trimmed or collapsed[: max_length - 1]}…"


def _coerce_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_valid_race_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except (TypeError, ValueError):
        return False


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
TRACK_SLUGS: Dict[str, str] = {}
TRACK_IDS_BY_SLUG: Dict[str, str] = {}


def _slugify_track_name(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "track"


for _track_id, _track_name in SUPPORTED_TRACKS.items():
    _slug = _slugify_track_name(_track_name)
    if _slug in TRACK_IDS_BY_SLUG and TRACK_IDS_BY_SLUG[_slug] != _track_id:
        _slug = f"{_slug}-{_track_id.lower()}"
    TRACK_SLUGS[_track_id] = _slug
    TRACK_IDS_BY_SLUG[_slug] = _track_id


def get_track_slug(track_id: str) -> str:
    return TRACK_SLUGS.get(track_id, _slugify_track_name(SUPPORTED_TRACKS.get(track_id, track_id)))


def get_track_id_from_slug(track_slug: str) -> Optional[str]:
    return TRACK_IDS_BY_SLUG.get((track_slug or "").strip().lower())


def _build_public_card_path(track_id: str, race_date: str) -> str:
    return f"/{get_track_slug(track_id)}/{race_date}"


def _build_public_race_path(track_id: str, race_date: str, race_number: int) -> str:
    return f"{_build_public_card_path(track_id, race_date)}/race-{race_number}"


def _build_public_record_path() -> str:
    return "/record"


def _build_public_recap_path(track_id: str, race_date: str) -> str:
    return f"{_build_public_record_path()}/{get_track_slug(track_id)}/{race_date}"


def _get_public_base_url(request: Request) -> str:
    configured = os.environ.get("PUBLIC_BASE_URL", "").strip()
    if configured:
        return configured.rstrip("/")
    base_url = getattr(request, "base_url", "http://testserver/")
    return str(base_url).rstrip("/")


def _to_public_absolute_url(request: Request, path: str) -> str:
    return f"{_get_public_base_url(request)}{path}"


def _build_card_status(race_date: str) -> str:
    tz_offset = int(os.environ.get("RACE_TZ_OFFSET_HOURS", "-7"))
    now_local = datetime.now(timezone(timedelta(hours=tz_offset)))
    today_str = now_local.strftime("%Y-%m-%d")
    end_of_racing_hour = int(os.environ.get("RACE_DAY_END_HOUR", "21"))
    if race_date > today_str:
        return "upcoming"
    if race_date == today_str and now_local.hour < end_of_racing_hour:
        return "live"
    return "completed"


def _build_card_meta_title(track_name: str, race_date: str) -> str:
    return f"{track_name} Betting Picks & Full Card Analysis - {race_date} | {BRAND_NAME}"


def _build_race_meta_title(track_name: str, race_date: str, race_number: int) -> str:
    return f"{track_name} Race {race_number} Strategy & Betting Picks - {race_date} | {BRAND_NAME}"


def _build_card_meta_description(card: Dict[str, Any], track_name: str, race_date: str) -> str:
    overview = _normalize_public_text(card.get("card_overview", ""), max_length=170)
    if overview:
        return overview

    races = card.get("races_json") or []
    if races:
        return _normalize_public_text(
            f"TrackStarAI full-card analysis for {track_name} on {race_date}. Explore every race with top picks, value plays, longshots, and betting strategy.",
            max_length=170,
        )

    return _normalize_public_text(
        f"TrackStarAI curated betting card for {track_name} on {race_date}.",
        max_length=170,
    )


def _build_race_meta_description(race: Dict[str, Any], track_name: str, race_date: str, race_number: int) -> str:
    picks: List[str] = []
    if race.get("top_pick"):
        picks.append(f"Top pick: {race['top_pick']}")
    if race.get("value_play"):
        picks.append(f"Value play: {race['value_play']}")
    if race.get("longshot"):
        picks.append(f"Longshot: {race['longshot']}")
    if picks:
        return _normalize_public_text(
            f"TrackStarAI picks for {track_name} Race {race_number} on {race_date}. {' '.join(picks)}.",
            max_length=170,
        )

    race_notes = _normalize_public_text(race.get("race_notes", ""), max_length=170)
    if race_notes:
        return race_notes

    return _normalize_public_text(
        f"TrackStarAI strategy and betting picks for {track_name} Race {race_number} on {race_date}.",
        max_length=170,
    )


def _build_record_index_meta_title() -> str:
    return f"30-Day Track Record & Betting Results | {BRAND_NAME}"


def _build_record_index_meta_description(summary: Dict[str, Any]) -> str:
    total_days = summary.get("total_days_recapped") or 0
    top_pick_rate = summary.get("top_pick_win_rate_pct") or 0
    exacta_rate = summary.get("exacta_hit_rate_pct") or 0
    trifecta_rate = summary.get("trifecta_hit_rate_pct") or 0
    return _normalize_public_text(
        f"TrackStarAI's 30-day verified track record across {total_days} recap days. Top pick win rate {top_pick_rate}%, exacta hit rate {exacta_rate}%, and trifecta hit rate {trifecta_rate}%.",
        max_length=170,
    )


def _build_recap_meta_title(track_name: str, race_date: str) -> str:
    return f"{track_name} Betting Recap & Results - {race_date} | {BRAND_NAME}"


def _build_recap_meta_description(record: Dict[str, Any], track_name: str, race_date: str) -> str:
    top_pick_wins = record.get("top_pick_wins", 0)
    top_pick_total = record.get("top_pick_total", 0)
    daily_score = record.get("daily_score", 0)
    exacta_hits = record.get("exacta_hits", 0)
    trifecta_hits = record.get("trifecta_hits", 0)
    best_winner = record.get("best_winner_horse") or ""
    best_winner_odds = record.get("best_winner_odds") or ""
    parts = [
        f"TrackStarAI recap for {track_name} on {race_date}.",
        f"Daily score: {daily_score}/100.",
        f"Top picks won: {top_pick_wins} of {top_pick_total}.",
        f"Exacta hits: {exacta_hits}.",
        f"Trifecta hits: {trifecta_hits}.",
    ]
    if best_winner:
        parts.append(f"Best winner: {best_winner}{f' ({best_winner_odds})' if best_winner_odds else ''}.")
    return _normalize_public_text(" ".join(parts), max_length=170)


def _prepare_public_recap_record(request: Request, record: Dict[str, Any]) -> Dict[str, Any]:
    recap = copy.deepcopy(record)
    track_id = recap.get("track_id") or ""
    race_date = recap.get("race_date") or ""
    track_name = SUPPORTED_TRACKS.get(track_id, track_id)
    recap["track_name"] = track_name
    recap["track_slug"] = get_track_slug(track_id)
    recap["public_url"] = _build_public_recap_path(track_id, race_date)
    recap["absolute_url"] = _to_public_absolute_url(request, recap["public_url"])
    recap["card_url"] = _build_public_card_path(track_id, race_date)
    recap["card_absolute_url"] = _to_public_absolute_url(request, recap["card_url"])
    recap["meta_title"] = _build_recap_meta_title(track_name, race_date)
    recap["meta_description"] = _build_recap_meta_description(recap, track_name, race_date)
    return recap


def _build_record_index_meta(request: Request, summary: Dict[str, Any]) -> Dict[str, Any]:
    record_index_path = _build_public_record_path()
    record_index_url = _to_public_absolute_url(request, record_index_path)
    return {
        "path": record_index_path,
        "absolute_url": record_index_url,
        "title": _build_record_index_meta_title(),
        "description": _build_record_index_meta_description(summary),
        "view_mode": "summary",
        "selected_key": None,
    }


def _build_record_structured_data(
    request: Request,
    *,
    title: str,
    description: str,
    canonical_url: str,
    records: List[Dict[str, Any]],
    selected_record: Optional[Dict[str, Any]],
) -> str:
    base_url = _get_public_base_url(request)
    payload: List[Dict[str, Any]] = [
        {
            "@context": "https://schema.org",
            "@type": "CollectionPage" if selected_record is None else "WebPage",
            "name": title,
            "description": description,
            "url": canonical_url,
            "isPartOf": {
                "@type": "WebSite",
                "name": BRAND_NAME,
                "url": f"{base_url}/",
            },
        },
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{base_url}/"},
                {"@type": "ListItem", "position": 2, "name": "Track Record", "item": f"{base_url}{_build_public_record_path()}"},
            ] + ([{
                "@type": "ListItem",
                "position": 3,
                "name": f"{selected_record.get('track_name', '')} {selected_record.get('race_date', '')}",
                "item": canonical_url,
            }] if selected_record else []),
        },
    ]

    item_list = []
    for index, record in enumerate(records, start=1):
        public_url = record.get("absolute_url")
        if not public_url:
            continue
        item_list.append(
            {
                "@type": "ListItem",
                "position": index,
                "url": public_url,
                "name": f"{record.get('track_name', record.get('track_id', ''))} recap for {record.get('race_date', '')}",
            }
        )

    if item_list:
        payload.append(
            {
                "@context": "https://schema.org",
                "@type": "ItemList",
                "name": "Recent track recap results",
                "itemListElement": item_list,
            }
        )

    return json.dumps(payload)


async def _build_record_page_context(
    request: Request,
    *,
    selected_track_id: Optional[str] = None,
    selected_race_date: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    session_manager = await app_state.ensure_session_manager()
    if not session_manager:
        return None

    summary: Dict[str, Any] = {}
    records: List[Dict[str, Any]] = []
    try:
        data = await asyncio.wait_for(session_manager.get_recap_summary_30d(), timeout=5.0)
        summary = data.get("summary", {})
        records = [_prepare_public_recap_record(request, record) for record in data.get("records", [])]
    except Exception as e:
        logger.warning(f"Failed to load recap summary for record page: {e}")

    selected_record = None
    if selected_track_id and selected_race_date:
        selected_record = next(
            (record for record in records if record.get("track_id") == selected_track_id and record.get("race_date") == selected_race_date),
            None,
        )
        if not selected_record:
            try:
                record = await session_manager.get_recap_record(selected_race_date, selected_track_id)
            except Exception as exc:
                logger.warning("Failed to load selected recap record for record page: %s", exc)
                record = None
            if record:
                selected_record = _prepare_public_recap_record(request, record)
                records = [
                    selected_record,
                    *[
                        existing for existing in records
                        if not (
                            existing.get("track_id") == selected_track_id and existing.get("race_date") == selected_race_date
                        )
                    ],
                ]

    if selected_track_id and selected_race_date and not selected_record:
        return {"error": "recap_not_found", "summary": summary, "records": records}

    index_meta = _build_record_index_meta(request, summary)

    recap_routes = {
        record["public_url"]: {
            "path": record["public_url"],
            "absolute_url": record["absolute_url"],
            "title": record["meta_title"],
            "description": record["meta_description"],
            "view_mode": "recap",
            "selected_key": f"{record.get('track_id')}::{record.get('race_date')}",
            "trackName": record.get("track_name"),
            "raceDate": record.get("race_date"),
            "dailyScore": record.get("daily_score"),
        }
        for record in records
    }

    selected_meta = index_meta if not selected_record else recap_routes[selected_record["public_url"]]
    record_page_data = {
        "index": index_meta,
        "recaps": recap_routes,
        "initialViewMode": selected_meta["view_mode"],
        "selectedKey": selected_meta["selected_key"],
    }

    return _template_context(
        request,
        selected_meta["title"],
        page_title=selected_meta["title"],
        summary=summary,
        records=records,
        view_mode=selected_meta["view_mode"],
        selected_record=selected_record,
        record_page_data=record_page_data,
        meta_description=selected_meta["description"],
        canonical_url=selected_meta["absolute_url"],
        og_title=selected_meta["title"],
        og_description=selected_meta["description"],
        og_url=selected_meta["absolute_url"],
        og_type="article" if selected_record else "website",
        twitter_title=selected_meta["title"],
        twitter_description=selected_meta["description"],
        structured_data_json=_build_record_structured_data(
            request,
            title=selected_meta["title"],
            description=selected_meta["description"],
            canonical_url=selected_meta["absolute_url"],
            records=records,
            selected_record=selected_record,
        ),
    )


def _build_structured_data(
    request: Request,
    *,
    track_name: str,
    race_date: str,
    full_card_url: str,
    canonical_url: str,
    title: str,
    description: str,
    view_mode: str,
    races: List[Dict[str, Any]],
    selected_race_number: Optional[int],
) -> str:
    base_url = _get_public_base_url(request)
    payload: List[Dict[str, Any]] = [
        {
            "@context": "https://schema.org",
            "@type": "CollectionPage" if view_mode == "full-card" else "WebPage",
            "name": title,
            "description": description,
            "url": canonical_url,
            "isPartOf": {
                "@type": "WebSite",
                "name": BRAND_NAME,
                "url": f"{base_url}/",
            },
        },
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{base_url}/"},
                {"@type": "ListItem", "position": 2, "name": f"{track_name} {race_date}", "item": full_card_url},
            ]
            + ([
                {
                    "@type": "ListItem",
                    "position": 3,
                    "name": f"Race {selected_race_number}",
                    "item": canonical_url,
                }
            ] if view_mode == "race" and selected_race_number else []),
        },
    ]

    race_items = []
    for index, race in enumerate(races, start=1):
        race_number = _coerce_int(race.get("race_number"))
        race_url = race.get("public_url")
        if not race_number or not race_url:
            continue
        race_items.append(
            {
                "@type": "ListItem",
                "position": index,
                "url": race_url,
                "name": f"{track_name} Race {race_number}",
            }
        )

    if race_items:
        payload.append(
            {
                "@context": "https://schema.org",
                "@type": "ItemList",
                "name": f"{track_name} Races for {race_date}",
                "itemListElement": race_items,
            }
        )

    return json.dumps(payload)


async def _hydrate_public_card(card: Dict[str, Any], race_date: str, track_id: str, session_manager) -> Dict[str, Any]:
    """Inject prediction and deep-dive data into a stored public card payload."""
    card_copy = copy.deepcopy(card)
    races_json = card_copy.get("races_json") or []
    session_id = card_copy.get("session_id")

    if session_id and session_manager:
        session_results = await session_manager.get_session_results(session_id)
        if session_results and "error" not in session_results:
            race_analyses = session_results.get("race_analyses", [])
            predictions_by_race = {r.get("race_number"): r.get("predictions", []) for r in race_analyses}

            for race_obj in races_json:
                race_num = race_obj.get("race_number")
                if race_num in predictions_by_race:
                    race_obj["predictions"] = predictions_by_race[race_num]

    _jt_sentinels = _EMPTY_FIELD_VALUES
    if session_manager and races_json:
        for race_obj in races_json:
            race_num = race_obj.get("race_number")
            if not race_num:
                continue
            cached_dive = await session_manager.get_race_deep_dive(race_date, track_id, race_num)
            if not cached_dive:
                continue
            dd_horses = cached_dive.get("deep_dive", {}).get("horses", [])
            dd_by_name = {(h.get("name") or "").strip().lower(): h for h in dd_horses}
            for pred in race_obj.get("predictions", []):
                pname = (pred.get("horse_name") or pred.get("name") or "").strip().lower()
                dd_horse = dd_by_name.get(pname)
                if not dd_horse:
                    continue
                dd_jockey = (dd_horse.get("jockey") or "").strip()
                dd_trainer = (dd_horse.get("trainer") or "").strip()
                cur_jockey = (pred.get("jockey") or "").strip()
                cur_trainer = (pred.get("trainer") or "").strip()
                if dd_jockey and cur_jockey.lower() in _jt_sentinels:
                    pred["jockey"] = dd_jockey
                if dd_trainer and cur_trainer.lower() in _jt_sentinels:
                    pred["trainer"] = dd_trainer

    return card_copy


async def _build_public_card_context(
    request: Request,
    *,
    track_id: str,
    race_date: str,
    view_mode: str,
    selected_race_number: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    session_manager = await app_state.ensure_session_manager()
    if not session_manager:
        return None

    card = await session_manager.get_published_curated_card(race_date, track_id)
    if not card:
        return None

    card = await _hydrate_public_card(card, race_date, track_id, session_manager)
    track_name = SUPPORTED_TRACKS.get(track_id, track_id)
    races_json = card.get("races_json") or []
    race_lookup: Dict[int, Dict[str, Any]] = {}

    for race_obj in races_json:
        race_number = _coerce_int(race_obj.get("race_number"))
        if not race_number:
            continue
        race_obj["race_number"] = race_number
        race_obj["public_url"] = _build_public_race_path(track_id, race_date, race_number)
        race_lookup[race_number] = race_obj

    if view_mode == "race" and selected_race_number not in race_lookup:
        return {"error": "race_not_found", "track_name": track_name}

    full_card_path = _build_public_card_path(track_id, race_date)
    full_card_url = _to_public_absolute_url(request, full_card_path)
    card["public_url"] = full_card_path

    card_meta = {
        "path": full_card_path,
        "absolute_url": full_card_url,
        "title": _build_card_meta_title(track_name, race_date),
        "description": _build_card_meta_description(card, track_name, race_date),
        "view_mode": "full-card",
        "race_number": None,
    }

    race_meta: Dict[str, Dict[str, Any]] = {}
    for race_number, race_obj in race_lookup.items():
        race_path = _build_public_race_path(track_id, race_date, race_number)
        race_meta[str(race_number)] = {
            "path": race_path,
            "absolute_url": _to_public_absolute_url(request, race_path),
            "title": _build_race_meta_title(track_name, race_date, race_number),
            "description": _build_race_meta_description(race_obj, track_name, race_date, race_number),
            "view_mode": "race",
            "race_number": race_number,
        }

    selected_meta = card_meta if view_mode == "full-card" else race_meta[str(selected_race_number)]
    public_page_data = {
        "trackId": track_id,
        "trackName": track_name,
        "trackSlug": get_track_slug(track_id),
        "raceDate": race_date,
        "fullCard": card_meta,
        "races": race_meta,
        "initialViewMode": view_mode,
        "initialRaceNumber": selected_race_number,
    }

    return _template_context(
        request,
        selected_meta["title"],
        card=card,
        race_date=race_date,
        track_id=track_id,
        track_name=track_name,
        card_status=_build_card_status(race_date),
        view_mode=view_mode,
        selected_race_number=selected_race_number,
        active_race=race_lookup.get(selected_race_number) if selected_race_number else None,
        full_card_url=full_card_path,
        meta_description=selected_meta["description"],
        canonical_url=selected_meta["absolute_url"],
        og_title=selected_meta["title"],
        og_description=selected_meta["description"],
        og_url=selected_meta["absolute_url"],
        og_type="article" if view_mode == "race" else "website",
        twitter_title=selected_meta["title"],
        twitter_description=selected_meta["description"],
        structured_data_json=_build_structured_data(
            request,
            track_name=track_name,
            race_date=race_date,
            full_card_url=full_card_url,
            canonical_url=selected_meta["absolute_url"],
            title=selected_meta["title"],
            description=selected_meta["description"],
            view_mode=view_mode,
            races=races_json,
            selected_race_number=selected_race_number,
        ),
        public_page_data=public_page_data,
    )

def get_track_country(track_id: str) -> str:
    """Return the country code for a track (defaults to 'USA')."""
    return TRACK_COUNTRIES.get(track_id, "USA")

def is_international_track(track_id: str) -> bool:
    """Return True if track is outside the USA."""
    return get_track_country(track_id) != "USA"

logger.info(f"Configured tracks: {SUPPORTED_TRACKS}")
logger.info(f"Track countries: {TRACK_COUNTRIES}")
logger.info(f"Track slugs: {TRACK_SLUGS}")

MODEL_OPTIONS = [MODEL_CATALOG[model_id] for model_id in MODEL_CATALOG]
MODEL_LOOKUP = MODEL_CATALOG
DEFAULT_LLM_MODEL = "x-ai/grok-4.20-beta"
DEFAULT_ADMIN_LLM_MODEL = "x-ai/grok-4.20-beta"
CARD_RETENTION_DAYS = int(os.environ.get("CARD_RETENTION_DAYS", "28"))
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
    betting_strategy_json: Optional[List] = None
    is_published: bool = False
    races: Optional[List] = None
    card_overview: str = ""

class RewriteRaceNotesRequest(BaseModel):
    session_id: str
    race_date: str
    track_id: str = "DMR"
    race_number: int
    top_pick: str = ""
    value_play: str = ""
    longshot: str = ""

class AdminRecomputeRequest(BaseModel):
    session_id: str
    race_date: str
    track_id: str = "DMR"

class AutoCurateRequest(BaseModel):
    session_id: str
    race_date: str
    track_id: str = "DMR"

class GenerateRecapRequest(BaseModel):
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
    live_cards: List[Dict] = []
    upcoming_cards: List[Dict] = []
    past_cards: List[Dict] = []

    # Use configured race timezone so card status is grounded in local track time
    tz_offset = int(os.environ.get("RACE_TZ_OFFSET_HOURS", "-7"))
    now_local = datetime.now(timezone(timedelta(hours=tz_offset)))
    today_str = now_local.strftime("%Y-%m-%d")
    current_hour = now_local.hour

    # After this hour (local), today's card is considered "completed"
    # Most US tracks finish last post by ~6pm; 21:00 gives generous buffer
    end_of_racing_hour = int(os.environ.get("RACE_DAY_END_HOUR", "21"))

    if session_manager:
        try:
            all_published = await asyncio.wait_for(
                session_manager.get_published_curated_cards(limit=30), timeout=2.0
            )
            for pc in all_published:
                pc["track_name"] = SUPPORTED_TRACKS.get(pc.get("track_id"), pc.get("track_id"))
                pc["card_url"] = _build_public_card_path(pc.get("track_id", ""), pc.get("race_date", ""))
                race_date = pc.get("race_date", "")

                if race_date > today_str:
                    # Future card — upcoming
                    pc["card_status"] = "upcoming"
                    upcoming_cards.append(pc)
                elif race_date == today_str:
                    if current_hour >= end_of_racing_hour:
                        # Today but racing is over
                        pc["card_status"] = "completed"
                        past_cards.append(pc)
                    else:
                        # Today and racing could still be on
                        pc["card_status"] = "live"
                        live_cards.append(pc)
                else:
                    # Past date
                    pc["card_status"] = "completed"
                    past_cards.append(pc)

            # Live: soonest first; Upcoming: soonest first; Past: most recent first
            live_cards.sort(key=lambda c: c.get("race_date", ""))
            upcoming_cards.sort(key=lambda c: c.get("race_date", ""))
        except Exception as e:
            logger.warning(f"Failed to load published curated cards for landing page: {e}")
    # Fetch 30-day track record summary for the stats widget
    track_record_summary = None
    if session_manager:
        try:
            track_record_summary = await asyncio.wait_for(
                session_manager.get_recap_summary_30d(), timeout=2.0
            )
            if not track_record_summary or not track_record_summary.get("records"):
                track_record_summary = None
        except Exception as e:
            logger.warning(f"Failed to load track record summary for landing page: {e}")
            track_record_summary = None

    return templates.TemplateResponse(
        request,
        "landing.html",
        _template_context(
            request,
            BRAND_NAME,
            live_cards=live_cards,
            upcoming_cards=upcoming_cards,
            past_cards=past_cards,
            track_record_summary=track_record_summary,
        ),
    )


@app.get("/record", response_class=HTMLResponse)
async def record_page(request: Request):
    """Public 30-day track record page."""
    context = await _build_record_page_context(request)
    if not context:
        index_meta = _build_record_index_meta(request, {})
        context = _template_context(
            request,
            index_meta["title"],
            page_title=index_meta["title"],
            summary={},
            records=[],
            view_mode="summary",
            selected_record=None,
            record_page_data={"index": index_meta, "recaps": {}, "initialViewMode": "summary", "selectedKey": None},
            meta_description=index_meta["description"],
            canonical_url=index_meta["absolute_url"],
            og_title=index_meta["title"],
            og_description=index_meta["description"],
            og_url=index_meta["absolute_url"],
            og_type="website",
            twitter_title=index_meta["title"],
            twitter_description=index_meta["description"],
            structured_data_json=_build_record_structured_data(
                request,
                title=index_meta["title"],
                description=index_meta["description"],
                canonical_url=index_meta["absolute_url"],
                records=[],
                selected_record=None,
            ),
        )
    return templates.TemplateResponse(request, "record.html", context)


@app.get("/record/{track_slug}/{race_date}", response_class=HTMLResponse)
async def recap_record_page(request: Request, track_slug: str, race_date: str):
    """Canonical public recap detail route."""
    track_id = get_track_id_from_slug(track_slug)
    if not track_id or not _is_valid_race_date(race_date):
        return templates.TemplateResponse(
            request,
            "error.html",
            _template_context(request, "Recap Not Found", error="The requested recap page could not be found."),
            status_code=404,
        )

    context = await _build_record_page_context(
        request,
        selected_track_id=track_id,
        selected_race_date=race_date,
    )
    if not context or context.get("error") == "recap_not_found":
        return templates.TemplateResponse(
            request,
            "error.html",
            _template_context(
                request,
                "Recap Not Found",
                error=f"No recap record found for {SUPPORTED_TRACKS.get(track_id, track_id)} on {race_date}.",
            ),
            status_code=404,
        )

    return templates.TemplateResponse(request, "record.html", context)


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
            model_options=_get_configured_model_options(),
            default_model=_get_default_model(DEFAULT_ADMIN_LLM_MODEL),
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
        # Fetch expected horses AND entry details in a single HTTP call
        if is_web_search_mode and fetch_equibase_all_data:
            expected_horses_by_race, equibase_entry_details = fetch_equibase_all_data(
                request.track_id, request.race_date, country=track_country
            )
            logger.info(
                "📊 Equibase data: expected_horses=%d races | entry_details=%d races | details_entries=%d",
                len(expected_horses_by_race),
                len(equibase_entry_details),
                sum(len(v) for v in equibase_entry_details.values()),
            )
        else:
            expected_horses_by_race = {}
            equibase_entry_details = {}
        # Derive race numbers from the data we already fetched — avoids another HTTP call
        if expected_horses_by_race:
            expected_race_numbers = sorted(expected_horses_by_race)
        elif is_web_search_mode:
            expected_race_numbers = fetch_equibase_expected_race_numbers(
                request.track_id, request.race_date, country=track_country
            )
        else:
            expected_race_numbers = []
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
                equibase_entry_details=equibase_entry_details,
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
                    equibase_entry_details=equibase_entry_details,
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
                    equibase_entry_details=equibase_entry_details,
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
                    equibase_entry_details=equibase_entry_details,
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
            equibase_entry_details=equibase_entry_details,
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

    sessions = await session_manager.get_recent_sessions(100)
    return JSONResponse(sessions)


@app.delete("/api/admin/session/{session_id}")
async def delete_session_endpoint(session_id: str, request: Request):
    """Delete an analysis session by ID (admin only)."""
    if not _auth_enabled():
        raise HTTPException(status_code=503, detail="Admin access is not configured on the server")
    if not _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin authentication required")

    session_manager = await app_state.ensure_session_manager()
    if not session_manager:
        raise HTTPException(status_code=503, detail="Session manager is not available")

    success = await session_manager.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete session")

    logger.info("🗑️ Admin deleted session %s", session_id)
    return JSONResponse({"status": "deleted", "session_id": session_id})


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
6. **Horse analysis** — Write a 2-3 sentence narrative assessment of each horse's realistic win chances. Cover key strengths, weaknesses, and the specific scenario in which the horse wins. Cite specific data points (speed figures, jockey stats, etc.).

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
      "form_notes": "Brief sharp condition assessment",
      "horse_analysis": "2-3 sentence narrative assessment of this horse's realistic win chances. Cover key strengths, weaknesses, and the specific scenario in which this horse wins. Be concrete and cite data."
    }}
  ],
  "deep_dive_summary": "Overall race dynamics and standout horses"
}}"""

    try:
        response = await openrouter_client.call_model(
            model=_get_default_model(DEFAULT_ADMIN_LLM_MODEL),
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
                            "horse_analysis": horse_data.get("horse_analysis", ""),
                        },
                        "quality_rating": 0.0,
                        "profile_url": "",
                    },
                )

        source_urls = merge_source_urls(
            source_urls=[],
            annotations=response.get("annotations", []) if isinstance(response, dict) else [],
        )

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


# ---------------------------------------------------------------------------
# Algorithmic Re-Rating — replaces LLM-subjective ratings with engine-computed
# ratings derived from deep-dive data (speed figures, form, jockey/trainer stats).
# ---------------------------------------------------------------------------

def _map_deep_dive_to_engine_format(cached: Dict) -> Dict:
    """Map deep-dive horse_data_cache record → RacePredictionEngine input.

    Deep-dive stores:
        last3_results: [{finish, speed_figure, distance, surface, …}]
        workouts:      [{distance, time, type, …}]
        smartpick:     {jockey_stats: {track_win_pct, …}, trainer_stats: …}

    Prediction engine expects:
        results:  [{speed_score, finish_position, distance, surface}]
        workouts: [{distance, time, workout_type}]
        smartpick: {jockey_stats: {win_percentage, …}, …}
    """
    results = []
    for r in cached.get("last3_results") or []:
        finish = r.get("finish", 10)
        if isinstance(finish, str):
            # Parse "1st of 8", "2nd", or just "3" formats
            import re as _re
            m = _re.match(r"(\d+)", finish)
            finish = int(m.group(1)) if m else 10
        results.append({
            "speed_score": r.get("speed_figure") or 0,
            "finish_position": int(finish) if isinstance(finish, (int, float)) else 10,
            "distance": r.get("distance", ""),
            "surface": r.get("surface", ""),
        })

    workouts = []
    for w in cached.get("workouts") or []:
        workouts.append({
            "distance": w.get("distance", ""),
            "time": w.get("time", ""),
            "workout_type": w.get("type", ""),
        })

    smartpick = cached.get("smartpick") or {}
    jockey_raw = smartpick.get("jockey_stats") or {}
    trainer_raw = smartpick.get("trainer_stats") or {}

    return {
        "results": results,
        "workouts": workouts,
        "smartpick": {
            "jockey_stats": {
                "win_percentage": jockey_raw.get("track_win_pct", 0),
                **jockey_raw,
            },
            "trainer_stats": {
                "win_percentage": trainer_raw.get("track_win_pct", 0),
                **trainer_raw,
            },
        },
    }


@app.post("/api/admin/recompute-ratings")
async def admin_recompute_ratings(request: AdminRecomputeRequest, http_request: Request = None):
    """Re-compute all race ratings using the algorithmic prediction engine and deep-dive data.

    After deep-dives populate the horse_data_cache with real speed figures,
    workouts, and jockey/trainer stats, this endpoint runs RacePredictionEngine
    to replace the LLM's subjective composite_rating values with algorithmically
    grounded ones using a transparent weighted formula.
    """
    if not _auth_enabled():
        raise HTTPException(status_code=503, detail="Admin access is not configured on the server")
    if http_request is None or not _is_admin(http_request):
        raise HTTPException(status_code=403, detail="Admin authentication required")

    session_manager = await app_state.ensure_session_manager()
    if not session_manager:
        raise HTTPException(status_code=503, detail="Session manager is not available")

    engine = app_state.prediction_engine
    if not engine:
        raise HTTPException(status_code=503, detail="Prediction engine is not available")

    # ── 1. Load session results ──────────────────────────────────────────────
    session_results = await session_manager.get_session_results(request.session_id)
    if "error" in session_results:
        raise HTTPException(status_code=404, detail=session_results["error"])

    race_analyses = session_results.get("race_analyses", [])
    if not race_analyses:
        raise HTTPException(status_code=404, detail="No race analyses found in session")

    recomputed_count = 0
    horses_updated = 0

    for race in race_analyses:
        predictions = race.get("predictions", [])
        if not predictions:
            continue

        # ── 2. Build engine inputs from cached deep-dive data ────────────────
        race_info = {
            "race_type": race.get("race_type", ""),
            "distance": race.get("distance", ""),
            "surface": race.get("surface", ""),
            "conditions": race.get("conditions", ""),
        }

        horses_for_engine = []
        horse_data_collection = {}
        has_deep_dive_data = False

        for pred in predictions:
            horse_name = pred.get("horse_name", "")
            if not horse_name:
                continue

            cached = await session_manager.get_cached_horse_data(
                request.race_date, horse_name
            )

            horses_for_engine.append({
                "name": horse_name,
                "jockey": pred.get("jockey", ""),
                "trainer": pred.get("trainer", ""),
                "post_position": pred.get("post_position", 0),
                "morning_line_odds": pred.get("morning_line_odds", ""),
            })

            if cached:
                mapped = _map_deep_dive_to_engine_format(cached)
                horse_data_collection[horse_name] = mapped
                if mapped.get("results"):
                    has_deep_dive_data = True
            else:
                horse_data_collection[horse_name] = {}

        # Only re-rate if we actually have deep-dive data for this race
        if not has_deep_dive_data:
            logger.info(
                "⏭ Skipping re-rating for race %s — no deep-dive data",
                race.get("race_number"),
            )
            continue

        # ── 3. Run the prediction engine ─────────────────────────────────────
        race_data_for_engine = {**race_info, "horses": horses_for_engine}
        engine_result = engine.predict_race(race_data_for_engine, horse_data_collection)
        engine_predictions = engine_result.get("predictions", [])

        # Build lookup by horse name
        engine_lookup = {
            ep.get("horse_name", ep.get("name", "")).strip().lower(): ep
            for ep in engine_predictions
        }

        # ── 4. Merge engine ratings back into the session predictions ────────
        for pred in predictions:
            horse_key = pred.get("horse_name", "").strip().lower()
            ep = engine_lookup.get(horse_key)
            if not ep:
                continue

            pred["_llm_composite_rating"] = pred.get("composite_rating")
            pred["_llm_factors"] = pred.get("factors")
            pred["composite_rating"] = ep.get("composite_rating", pred["composite_rating"])
            pred["win_probability"] = ep.get("win_probability", pred.get("win_probability", 0))

            engine_factors = ep.get("factors")
            if engine_factors:
                pred["factors"] = {
                    "speed_rating": engine_factors.get("speed_rating", engine_factors.get("speed", 0)),
                    "form_rating": engine_factors.get("form_rating", engine_factors.get("form", 0)),
                    "class_rating": engine_factors.get("class_rating", engine_factors.get("class", 0)),
                    "workout_rating": engine_factors.get("workout_rating", engine_factors.get("workout", 0)),
                }
            horses_updated += 1

        # Re-sort predictions by composite_rating (engine may reorder them)
        predictions.sort(key=lambda p: p.get("composite_rating", 0), reverse=True)
        race["predictions"] = predictions
        recomputed_count += 1

    # ── 5. Save updated session results ──────────────────────────────────────
    await session_manager.save_session_results(request.session_id, session_results)

    logger.info(
        "✅ Algorithmic re-rating complete | session=%s | races=%d | horses=%d",
        request.session_id, recomputed_count, horses_updated,
    )

    return JSONResponse({
        "session_id": request.session_id,
        "races_recomputed": recomputed_count,
        "horses_updated": horses_updated,
        "message": f"Re-rated {horses_updated} horses across {recomputed_count} races using prediction engine",
    })



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
        horse_analysis = dd_horse.get("horse_analysis", "")
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
        if horse_analysis:
            block += f"  Analysis: {horse_analysis}\n"
        if js:
            block += f"  Jockey: Track{js.get('track_win_pct','?')}% Dist{js.get('distance_win_pct','?')}% 30d:{js.get('last_30_days','?')}\n"
        if ts:
            block += f"  Trainer: Track{ts.get('track_win_pct','?')}% Dist{ts.get('distance_win_pct','?')}% 30d:{ts.get('last_30_days','?')}\n"
        block += f"  Recent: {recent_str}\n"
        block += f"  Workouts: {workout_str}\n"
        return block

    race_sections = []
    horse_names_by_race: dict = {}  # race_number -> list of horse names
    horse_notes_by_race: dict = {}  # race_number -> {horse_name: analysis}

    # Instantiate strategy engine once (methods are pure — no AI calls needed)
    _strategy_engine = AIAnalysisEnhancer(openrouter_client) if AIAnalysisEnhancer else None

    for race in sorted(race_analyses, key=lambda r: r.get("race_number", 0)):
        race_num = race.get("race_number", 0)
        cached_dive = await session_manager.get_race_deep_dive(
            request.race_date, request.track_id, race_num
        )
        dd_data = cached_dive.get("deep_dive", {}) if cached_dive else {}
        dd_by_name = {h.get("name", "").lower(): h for h in dd_data.get("horses", [])}

        predictions = race.get("predictions", [])

        # Apply speed-figure Bayesian adjustment to composite_rating and win_probability
        if dd_by_name and predictions:
            predictions = _apply_speed_figure_adjustment(list(predictions), dd_by_name)

        horse_names_by_race[race_num] = [
            (p.get("horse_name") or p.get("name") or "") for p in predictions
        ]

        # Collect per-horse narrative analyses for the UI
        race_horse_notes = {}
        for h_dd in dd_data.get("horses", []):
            h_name = h_dd.get("name", "")
            h_analysis = h_dd.get("horse_analysis", "")
            if h_name and h_analysis:
                race_horse_notes[h_name] = h_analysis
        if race_horse_notes:
            horse_notes_by_race[race_num] = race_horse_notes

        section = (
            f"RACE {race_num} — {race.get('race_type','?')} | "
            f"{race.get('distance','?')} | {race.get('surface','?')}\n"
        )
        if dd_data.get("deep_dive_summary"):
            section += f"DeepDiveSummary: {dd_data['deep_dive_summary']}\n"
        for pred in predictions:
            name = (pred.get("horse_name") or pred.get("name") or "").lower()
            section += _build_horse_block(pred, dd_by_name.get(name, {}))

        # ── Compute pre-built strategy signals and append to the section ──
        if _strategy_engine and predictions:
            try:
                exotic_grp = _strategy_engine._compute_exotic_grouping(predictions)
                upset_hdg = _strategy_engine._compute_upset_hedge(predictions)
                ev_exotics = _strategy_engine._compute_high_odds_value_exotics(predictions)

                section += "  [PRE-COMPUTED STRATEGY SIGNALS]\n"

                # Strategy 1 — Consecutive-ranking exotic grouping
                if exotic_grp and exotic_grp.get("triggered"):
                    ex = exotic_grp.get("exacta", {})
                    tri = exotic_grp.get("trifecta", {})
                    ex_combo = "-".join(ex.get("horses", []))
                    tri_combo = "-".join(tri.get("horses", []))
                    section += (
                        f"  S1-ConsecutiveGrouping ({exotic_grp.get('conviction_level','').upper()}): "
                        f"{exotic_grp.get('trigger_reason','')} | "
                        f"Exacta {ex_combo} (Harville prob {ex.get('harville_probability','')}) | "
                        f"Trifecta {tri_combo} (Harville prob {tri.get('harville_probability','')})\n"
                    )
                else:
                    section += "  S1-ConsecutiveGrouping: not triggered (no dominant top pick)\n"

                # Strategy 2 — Upset play with favorite hedge
                if upset_hdg and upset_hdg.get("triggered"):
                    fav_info = upset_hdg.get("heavy_favorite", {})
                    upset_info = upset_hdg.get("upset_candidate", {})
                    hedge = upset_hdg.get("hedge_exacta", {})
                    section += (
                        f"  S2-UpsetHedge: Fade {fav_info.get('horse','')} "
                        f"({fav_info.get('win_probability','')}% win prob, "
                        f"ML {fav_info.get('morning_line','')}) | "
                        f"Upset pick: {upset_info.get('horse','')} "
                        f"(rating gap {upset_info.get('rating_gap','')}pts) | "
                        f"{hedge.get('description','')} "
                        f"(Harville prob {hedge.get('harville_probability','')})\n"
                    )
                else:
                    section += "  S2-UpsetHedge: not triggered (no heavy favorite detected)\n"

                # Strategy 3 — High-odds EV exotics (top 3 plays)
                if ev_exotics:
                    section += "  S3-HighOddsEV (top plays by expected value):\n"
                    for play in ev_exotics[:3]:
                        combo = "-".join(play.get("horses", []))
                        ev_val = play.get("expected_value", 0.0)
                        section += (
                            f"    {play.get('bet_type','').upper()} "
                            f"{combo} | "
                            f"EV={ev_val:.3f} ({play.get('ev_margin_pct', 0):.0f}% edge) | "
                            f"Model prob {play.get('harville_probability','')} vs "
                            f"Market prob {play.get('market_implied_prob','')}\n"
                        )
                else:
                    section += "  S3-HighOddsEV: no EV-positive combos found above threshold\n"

                # Longshot value flags (Prelec-corrected misperception signals)
                if _strategy_engine and predictions:
                    longshot_flags = _strategy_engine._compute_longshot_flags(predictions)
                    if longshot_flags:
                        section += '  S4-LongshotValueFlags:\n'
                        for flag in longshot_flags:
                            section += f"    {flag.get('flag_summary','')}\n"
                    else:
                        section += '  S4-LongshotValueFlags: none detected (no ML odds >= 10-1 with EV signal)\n'

            except Exception as _strat_err:
                logger.warning("Strategy signal computation failed for race %s: %s", race_num, _strat_err)

        race_sections.append(section)

    prompt = f"""You are a professional horse racing handicapper. You have the full race card for {track_full} on {request.race_date} — including the initial AI race card analysis, deep-dive research (workouts, recent form, jockey/trainer stats), and pre-computed quantitative strategy signals for each race.

Re-analyze the entire card using ALL of this combined information. For every race, identify the three best betting angles and write editorial-quality race notes. Then write an overall card overview.

FULL RACE CARD DATA (each race includes [PRE-COMPUTED STRATEGY SIGNALS]):
{'='*60}
{chr(10).join(race_sections)}
{'='*60}

STRATEGY SIGNAL LEGEND:
- S1-ConsecutiveGrouping: When one horse stands apart, exacta/trifecta combos using horses ranked consecutively by composite rating. Use these as the structural backbone of exacta/trifecta tickets.
- S2-UpsetHedge: When a heavy favorite exists, the upset candidate is identified and a hedge exacta (upset on top, favorite underneath) is pre-computed. If this signal is triggered, include the upset angle and hedge exacta in the betting strategy.
- S3-HighOddsEV: Exotic combinations with positive expected value after takeout. If any EV plays are listed, include at least the top one as a small-investment speculative exotic in the betting strategy.
- S4-LongshotValueFlags: Longshots where Prelec probability correction indicates positive EV versus market. If any flags are listed, reference the longshot by name in the race analysis and include as a speculative win or exacta add in the betting strategy.

For each race return:
- top_pick: the horse name with the highest win probability after re-analysis
- value_play: a horse with strong credentials likely undervalued at the windows
- longshot: a horse with realistic upset potential at big odds (use S2-UpsetHedge candidate if triggered)
- race_notes: 2-3 sentences of editorial analysis explaining the picks and race shape
- betting_strategy: specific bets using POST POSITION NUMBERS only. Incorporate the pre-computed strategy signals:
  * Always anchor the strategy on the top pick (win or exacta key)
  * If S1 is triggered, include the consecutive-ranking exacta and/or trifecta
  * If S2 is triggered, include the upset/hedge exacta
  * If S3 has EV plays, include the top EV exotic as a speculative add
  * Format: "Win on #X, exacta key X/Y,Z, trifecta X with Y,Z — hedge: upset X over Y (exacta)"

Also return:
- card_overview: 3-4 sentence overview of the overall card themes, standout races, and key angles for the day

Also return for each race a structured `bets` array that decomposes the free-text betting_strategy into individually trackable wagers. Each element must use this exact schema:
  {{ "type": "WIN"|"EXACTA"|"TRIFECTA"|"EXACTA_HEDGE", "keys": [post_numbers...], "with": [post_numbers...], "amount_suggestion": "$2" }}
  - WIN: keys=[single post], with=[]
  - EXACTA: keys=[key horse post], with=[other posts]
  - TRIFECTA: keys=[key horse post], with=[other posts]
  - EXACTA_HEDGE: keys=[upset post, favorite post], with=[]

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
      "betting_strategy": "Win on #X, exacta key X/Y,Z, trifecta X with Y,Z...",
      "bets": [
        {{ "type": "WIN", "keys": [5], "with": [], "amount_suggestion": "$2" }},
        {{ "type": "EXACTA", "keys": [5], "with": [3, 8], "amount_suggestion": "$1" }},
        {{ "type": "TRIFECTA", "keys": [5], "with": [3, 8, 2], "amount_suggestion": "$1" }}
      ]
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
            model=_get_default_model(DEFAULT_ADMIN_LLM_MODEL),
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
            "horse_notes_by_race": horse_notes_by_race,
        })

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Full-card auto-curation failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/admin/rewrite-race-notes")
async def rewrite_race_notes(request: RewriteRaceNotesRequest, http_request: Request = None):
    """Rewrite race notes and betting strategy when an admin changes pick selections."""
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

    # ── 1. Fetch session race data ────────────────────────────────────────────
    session_results = await session_manager.get_session_results(request.session_id)
    if "error" in session_results:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_results['error']}")

    race_analyses = session_results.get("race_analyses", [])
    target_race = next(
        (r for r in race_analyses if r.get("race_number") == request.race_number), None
    )
    if not target_race:
        raise HTTPException(status_code=404, detail=f"Race {request.race_number} not found in session")

    predictions = target_race.get("predictions", [])

    # ── 2. Fetch deep-dive data ───────────────────────────────────────────────
    cached_dive = await session_manager.get_race_deep_dive(
        request.race_date, request.track_id, request.race_number
    )
    dd_data = cached_dive.get("deep_dive", {}) if cached_dive else {}
    dd_by_name = {h.get("name", "").lower(): h for h in dd_data.get("horses", [])}

    # Apply the same Bayesian speed-figure adjustment used in auto-curation
    if dd_by_name and predictions:
        predictions = _apply_speed_figure_adjustment(list(predictions), dd_by_name)

    # ── 3. Build horse summaries ──────────────────────────────────────────────
    horse_summaries = []
    for pred in predictions:
        name = pred.get("horse_name") or pred.get("name") or ""
        dd_horse = dd_by_name.get(name.lower(), {})
        composite = pred.get("composite_rating", "?")
        win_prob = pred.get("win_probability", "?")
        factors = pred.get("factors") or {}
        analysis = dd_horse.get("horse_analysis", "")
        form_notes = dd_horse.get("form_notes", "")
        js = dd_horse.get("jockey_stats") or {}
        ts = dd_horse.get("trainer_stats") or {}

        summary = f"- {name} (Post {pred.get('post_position','?')}, Rating:{composite}, WinProb:{win_prob}%)"
        if factors:
            summary += f" | Spd:{factors.get('speed_rating',0)} Form:{factors.get('form_rating',0)} Cls:{factors.get('class_rating',0)}"
        if analysis:
            summary += f"\n  Analysis: {analysis}"
        elif form_notes:
            summary += f"\n  Form: {form_notes}"
        if js:
            summary += f"\n  Jockey: Track{js.get('track_win_pct','?')}% 30d:{js.get('last_30_days','?')}"
        if ts:
            summary += f"\n  Trainer: Track{ts.get('track_win_pct','?')}% 30d:{ts.get('last_30_days','?')}"
        horse_summaries.append(summary)

    race_info = (
        f"Race {request.race_number} at {track_full} on {request.race_date} — "
        f"{target_race.get('race_type','?')} | {target_race.get('distance','?')} | {target_race.get('surface','?')}"
    )

    prompt = f"""You are a professional horse racing handicapper writing editorial-quality race notes.

The admin has selected the following picks for this race. Write race notes and a betting strategy that logically explain WHY these specific horses were chosen, citing concrete data points from the horse analyses below.

RACE: {race_info}

ADMIN'S PICKS:
- Top Pick: {request.top_pick or '(none)'}
- Value Play: {request.value_play or '(none)'}
- Longshot: {request.longshot or '(none)'}

ALL HORSES IN THE FIELD:
{chr(10).join(horse_summaries)}

Write:
1. race_notes: 2-3 sentences of editorial analysis explaining why the top pick is the strongest play, why the value play is undervalued, and why the longshot has upset potential. Be specific — cite speed figures, form, jockey/trainer stats, or running style.
2. betting_strategy: specific bet types using POST POSITION NUMBERS only (e.g. "Win on 5, exacta key 5/3,8, trifecta 5 with 3,8,2"). NEVER use horse names in the strategy — use only post numbers.

IMPORTANT FORMATTING RULES:
- race_notes should be 2-3 sentences. Match the concise editorial style of a professional tip sheet.
- betting_strategy must reference horses ONLY by their post position numbers, formatted like: "Win on 5, exacta key 5/3,8, trifecta 5 with 3,8,2"

Return ONLY valid JSON:
{{
  "race_notes": "Editorial analysis...",
  "betting_strategy": "Win on #, exacta key #/#,#, trifecta # with #,#,#"
}}"""

    logger.info(
        "✏️ REWRITE-NOTES: session=%s | race=%s | top=%s | value=%s | longshot=%s",
        request.session_id, request.race_number,
        request.top_pick, request.value_play, request.longshot,
    )

    try:
        response = await openrouter_client.call_model(
            model=_get_default_model(DEFAULT_ADMIN_LLM_MODEL),
            task_type="analysis",
            prompt=prompt,
            context={
                "race_date": request.race_date,
                "track_id": request.track_id,
                "race_number": request.race_number,
            },
            max_tokens=1000,
            temperature=0.3,
            return_metadata=True,
            response_format={"type": "json_object"},
        )

        content = response.get("content", "") if isinstance(response, dict) else str(response)
        if not content:
            raise HTTPException(status_code=502, detail="AI returned empty content for notes rewrite")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            import re as _re
            match = _re.search(r'\{.*\}', content, _re.DOTALL)
            if match:
                parsed = json.loads(match.group())
            else:
                raise HTTPException(status_code=502, detail="Could not parse AI notes rewrite response as JSON")

        logger.info("✅ REWRITE-NOTES complete | race=%s", request.race_number)
        return JSONResponse({
            "race_number": request.race_number,
            "race_notes": parsed.get("race_notes", ""),
            "betting_strategy": parsed.get("betting_strategy", ""),
        })

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Rewrite-notes failed for race {request.race_number}: {exc}")
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
            betting_strategy_json=request.betting_strategy_json,
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
            "card_url": _build_public_card_path(request.track_id, request.race_date),
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

    # Cross-reference recap records so the UI can show has_recap flag
    for card in cards:
        card["track_name"] = SUPPORTED_TRACKS.get(card.get("track_id"), card.get("track_id"))
        card["card_url"] = _build_public_card_path(card.get("track_id", ""), card.get("race_date", ""))
        recap = await session_manager.get_recap_record(card.get("race_date", ""), card.get("track_id", ""))
        if recap:
            card["has_recap"] = True
            card["recap_daily_score"] = recap.get("daily_score", 0)
            card["recap_top_pick_wins"] = recap.get("top_pick_wins", 0)
            card["recap_top_pick_total"] = recap.get("top_pick_total", 0)
        else:
            card["has_recap"] = False

    return JSONResponse(cards)


@app.delete("/api/admin/curated-card/{card_id}")
async def delete_curated_card_endpoint(card_id: str, request: Request):
    """Delete a curated card by ID (admin only)."""
    if not _auth_enabled():
        raise HTTPException(status_code=503, detail="Admin access is not configured on the server")
    if not _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin authentication required")

    session_manager = await app_state.ensure_session_manager()
    if not session_manager:
        raise HTTPException(status_code=503, detail="Session manager is not available")

    success = await session_manager.delete_curated_card(card_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete curated card")

    logger.info("🗑️ Admin deleted curated card %s", card_id)
    return JSONResponse({"status": "deleted", "id": card_id})


@app.get("/api/admin/deep-dives")
async def list_deep_dives_endpoint(request: Request, race_date: str = None, track_id: str = None):
    """List deep-dive cache entries, optionally filtered by race_date and track_id (admin only)."""
    if not _auth_enabled():
        raise HTTPException(status_code=503, detail="Admin access is not configured on the server")
    if not _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin authentication required")

    session_manager = await app_state.ensure_session_manager()
    if not session_manager:
        raise HTTPException(status_code=503, detail="Session manager is not available")

    entries = await session_manager.list_deep_dives(race_date=race_date, track_id=track_id)
    return JSONResponse(entries)


@app.delete("/api/admin/deep-dive/{race_date}/{track_id}/{race_number}")
async def delete_deep_dive_endpoint(race_date: str, track_id: str, race_number: int, request: Request):
    """Delete a single deep-dive cache entry (admin only)."""
    if not _auth_enabled():
        raise HTTPException(status_code=503, detail="Admin access is not configured on the server")
    if not _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin authentication required")

    session_manager = await app_state.ensure_session_manager()
    if not session_manager:
        raise HTTPException(status_code=503, detail="Session manager is not available")

    success = await session_manager.delete_deep_dive(race_date, track_id, race_number)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete deep dive entry")

    logger.info("🗑️ Admin deleted deep dive %s/%s/race-%s", race_date, track_id, race_number)
    return JSONResponse({"status": "deleted", "race_date": race_date, "track_id": track_id, "race_number": race_number})


@app.post("/api/admin/generate-recap")
async def generate_recap(request: GenerateRecapRequest, http_request: Request = None):
    """Generate a recap for a past curated card by comparing picks to official Equibase results via Grok web search."""
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

    # ── 1. Load the curated card ──────────────────────────────────────────────
    card = await session_manager.get_curated_card(request.race_date, request.track_id)
    if not card:
        raise HTTPException(status_code=404, detail=f"No curated card found for {request.race_date} / {request.track_id}")

    races = card.get("races_json") or []
    if not races:
        raise HTTPException(status_code=400, detail="Curated card has no races data")

    track_full = SUPPORTED_TRACKS.get(request.track_id, request.track_id)

    # ── 2. Build per-race picks summary for Grok ─────────────────────────────
    picks_summary = []
    for race in races:
        rn = race.get("race_number", "?")
        picks_summary.append(
            f"Race {rn}: Top Pick={race.get('top_pick','N/A')}, "
            f"Value Play={race.get('value_play','N/A')}, "
            f"Longshot={race.get('longshot','N/A')}, "
            f"Betting Strategy={race.get('betting_strategy','N/A')}"
        )

    prompt = f"""You are auditing horse racing picks against official results. Look up the official race results for {track_full} on {request.race_date} from Equibase or any reliable source.

For each race below, compare our picks to the actual results. Return a JSON object with the structure shown below.

OUR PICKS:
{chr(10).join(picks_summary)}

For each race, determine:
1. Did the top_pick WIN (finish 1st)?
2. Did the value_play WIN (finish 1st)?
3. Did the longshot WIN (finish 1st)?
4. exacta_hit: Set to true ONLY if the betting_strategy explicitly specifies an exacta wager AND the exact combination mentioned finished in the correct 1st-2nd order (or boxed). Do NOT set true simply because the top pick placed — exacta_hit requires both a stated exacta bet in the strategy AND that specific combo hitting. If the betting_strategy does not mention an exacta, set exacta_hit=false.
5. trifecta_hit: Set to true ONLY if the betting_strategy explicitly specifies a trifecta wager AND that exact 1st-2nd-3rd combination hit. If the betting_strategy does not mention a trifecta, set trifecta_hit=false.
6. The actual winner's name and odds
7. The official exacta and trifecta payouts for the race (per $2 base) — report the actual race result payouts regardless of whether our bet hit. Set to 0.0 if not available.

Return ONLY valid JSON:
{{
  "races": [
    {{
      "race_number": 1,
      "winner": "Horse Name",
      "winner_odds": "5-2",
      "place_horse": "2nd Place Horse",
      "show_horse": "3rd Place Horse",
      "top_pick_won": true,
      "value_play_won": false,
      "longshot_won": false,
      "exacta_hit": false,
      "trifecta_hit": false,
      "exacta_payout": 0.0,
      "trifecta_payout": 0.0,
      "recap_note": "Brief note on the outcome...",
      "data_available": true
    }}
  ]
}}

If results for a race are not available, set data_available=false and leave other fields at defaults. Do NOT guess — only report confirmed results."""

    logger.info(
        "📊 GENERATE-RECAP: date=%s | track=%s | races=%d",
        request.race_date, request.track_id, len(races),
    )

    try:
        response = await openrouter_client.call_model(
            model=_get_default_model(DEFAULT_ADMIN_LLM_MODEL),
            task_type="analysis",
            prompt=prompt,
            context={"race_date": request.race_date, "track_id": request.track_id},
            max_tokens=4000,
            temperature=0.1,
            return_metadata=True,
            response_format={"type": "json_object"},
            plugins=[{"id": "web"}],
        )

        content = response.get("content", "") if isinstance(response, dict) else str(response)
        if not content:
            raise HTTPException(status_code=502, detail="Grok returned empty content for recap")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            import re as _re
            match = _re.search(r'\{.*\}', content, _re.DOTALL)
            if match:
                parsed = json.loads(match.group())
            else:
                raise HTTPException(status_code=502, detail="Could not parse Grok recap response as JSON")

        recap_races = parsed.get("races", [])

        # ── 3. Score the recap ────────────────────────────────────────────────
        # 13 max points per race:
        #   top_pick_won=3, value_play_won=2, longshot_won=2,
        #   exacta_hit=3, trifecta_hit=3
        total_score = 0.0
        max_possible = 0.0
        top_pick_wins = 0
        top_pick_total = 0
        value_play_wins = 0
        value_play_total = 0
        longshot_wins = 0
        longshot_total = 0
        exacta_hits = 0
        exacta_total = 0
        trifecta_hits = 0
        trifecta_total = 0
        best_winner_horse = ""
        best_winner_odds = ""
        best_winner_race = 0
        best_exacta_payout = 0.0
        best_exacta_race = 0
        best_trifecta_payout = 0.0
        best_trifecta_race = 0

        for rr in recap_races:
            if not rr.get("data_available", True):
                continue

            rn = rr.get("race_number", 0)
            max_possible += 13

            if rr.get("top_pick_won"):
                total_score += 3
                top_pick_wins += 1
            top_pick_total += 1

            if rr.get("value_play_won"):
                total_score += 2
                value_play_wins += 1
            value_play_total += 1

            if rr.get("longshot_won"):
                total_score += 2
                longshot_wins += 1
            longshot_total += 1

            if rr.get("exacta_hit"):
                total_score += 3
                exacta_hits += 1
            exacta_total += 1

            if rr.get("trifecta_hit"):
                total_score += 3
                trifecta_hits += 1
            trifecta_total += 1

            # Track best winner odds (parse "X-Y" to numeric)
            odds_str = rr.get("winner_odds", "")
            if odds_str and rr.get("top_pick_won"):
                try:
                    parts = str(odds_str).replace("/", "-").split("-")
                    odds_val = float(parts[0]) / float(parts[1]) if len(parts) >= 2 else float(parts[0])
                except (ValueError, ZeroDivisionError, IndexError):
                    odds_val = 0
                # Compare to current best
                try:
                    best_parts = str(best_winner_odds).replace("/", "-").split("-") if best_winner_odds else ["0"]
                    best_val = float(best_parts[0]) / float(best_parts[1]) if len(best_parts) >= 2 else float(best_parts[0])
                except (ValueError, ZeroDivisionError, IndexError):
                    best_val = 0
                if odds_val > best_val:
                    best_winner_odds = odds_str
                    best_winner_horse = rr.get("winner", "")
                    best_winner_race = rn

            # Only track best payout when OUR bet actually hit
            ep = rr.get("exacta_payout", 0) or 0
            if rr.get("exacta_hit") and ep > best_exacta_payout:
                best_exacta_payout = ep
                best_exacta_race = rn

            tp = rr.get("trifecta_payout", 0) or 0
            if rr.get("trifecta_hit") and tp > best_trifecta_payout:
                best_trifecta_payout = tp
                best_trifecta_race = rn

        # Normalize to 0-100 scale
        daily_score = round((total_score / max_possible * 100), 1) if max_possible > 0 else 0.0

        # ── 4. Persist to DB ──────────────────────────────────────────────────
        # Build enriched recap JSON for storage
        for rr in recap_races:
            rn = rr.get("race_number", 0)
            orig = next((r for r in races if r.get("race_number") == rn), {})
            rr["our_top_pick"] = orig.get("top_pick", "")
            rr["our_value_play"] = orig.get("value_play", "")
            rr["our_longshot"] = orig.get("longshot", "")
            rr["hits"] = {
                "top_pick_won": rr.get("top_pick_won", False),
                "value_play_won": rr.get("value_play_won", False),
                "longshot_won": rr.get("longshot_won", False),
                "exacta_hit": rr.get("exacta_hit", False),
                "trifecta_hit": rr.get("trifecta_hit", False),
            }

        record_id = await session_manager.save_recap_record(
            race_date=request.race_date,
            track_id=request.track_id,
            races_recap_json=json.dumps(recap_races),
            daily_score=daily_score,
            max_possible_score=max_possible,
            top_pick_wins=top_pick_wins,
            top_pick_total=top_pick_total,
            value_play_wins=value_play_wins,
            value_play_total=value_play_total,
            longshot_wins=longshot_wins,
            longshot_total=longshot_total,
            exacta_hits=exacta_hits,
            exacta_total=exacta_total,
            trifecta_hits=trifecta_hits,
            trifecta_total=trifecta_total,
            best_winner_horse=best_winner_horse,
            best_winner_odds=best_winner_odds,
            best_winner_race=best_winner_race,
            best_exacta_payout=best_exacta_payout,
            best_exacta_race=best_exacta_race,
            best_trifecta_payout=best_trifecta_payout,
            best_trifecta_race=best_trifecta_race,
        )

        logger.info(
            "✅ RECAP saved | date=%s | track=%s | score=%.1f | id=%s",
            request.race_date, request.track_id, daily_score, record_id,
        )

        return JSONResponse({
            "id": record_id,
            "daily_score": daily_score,
            "races": recap_races,
            "summary": {
                "top_pick_wins": top_pick_wins,
                "top_pick_total": top_pick_total,
                "exacta_hits": exacta_hits,
                "trifecta_hits": trifecta_hits,
            },
        })

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Generate recap failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/robots.txt")
async def robots_txt(request: Request):
    sitemap_url = f"{_get_public_base_url(request)}/sitemap.xml"
    content = "\n".join([
        "User-agent: *",
        "Allow: /",
        "",
        f"Sitemap: {sitemap_url}",
    ])
    return Response(content=content, media_type="text/plain")


@app.get("/sitemap.xml")
async def sitemap_xml(request: Request):
    session_manager = await app_state.ensure_session_manager()
    seen_paths = set()
    entries: List[tuple[str, Optional[str]]] = [
        ("/", None),
        ("/record", None),
    ]

    if session_manager:
        try:
            published_cards = await asyncio.wait_for(
                session_manager.get_published_curated_cards(limit=500), timeout=5.0
            )
            for card in published_cards:
                track_id = card.get("track_id") or ""
                race_date = card.get("race_date") or ""
                if not track_id or not race_date:
                    continue
                lastmod = card.get("updated_at") or card.get("created_at")
                entries.append((_build_public_card_path(track_id, race_date), lastmod))
                for race in card.get("races_json") or []:
                    race_number = _coerce_int(race.get("race_number"))
                    if race_number:
                        entries.append((_build_public_race_path(track_id, race_date, race_number), lastmod))
        except Exception as exc:
            logger.warning("Failed to build sitemap from published cards: %s", exc)

        try:
            recap_data = await asyncio.wait_for(session_manager.get_recap_summary_30d(), timeout=5.0)
            for record in recap_data.get("records", []):
                track_id = record.get("track_id") or ""
                race_date = record.get("race_date") or ""
                if not track_id or not race_date:
                    continue
                lastmod = record.get("updated_at") or record.get("created_at") or race_date
                entries.append((_build_public_recap_path(track_id, race_date), lastmod))
        except Exception as exc:
            logger.warning("Failed to build sitemap from recap records: %s", exc)

    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, lastmod in entries:
        if not path or path in seen_paths:
            continue
        seen_paths.add(path)
        absolute_url = xml_escape(_to_public_absolute_url(request, path))
        lines.append("  <url>")
        lines.append(f"    <loc>{absolute_url}</loc>")
        if lastmod:
            lines.append(f"    <lastmod>{xml_escape(str(lastmod))}</lastmod>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return Response(content="\n".join(lines), media_type="application/xml")


@app.get("/card/{race_date}/{track_id}", response_class=HTMLResponse)
async def curated_card_page(request: Request, race_date: str, track_id: str):
    """Legacy public card URL — redirect to the canonical full-card route."""
    normalized_track_id = (track_id or "").upper()
    if normalized_track_id not in SUPPORTED_TRACKS or not _is_valid_race_date(race_date):
        return templates.TemplateResponse(
            request,
            "error.html",
            _template_context(
                request,
                "Card Not Found",
                error=f"No curated card found for {SUPPORTED_TRACKS.get(normalized_track_id, normalized_track_id or track_id)} on {race_date}.",
            ),
            status_code=404,
        )
    return RedirectResponse(_build_public_card_path(normalized_track_id, race_date), status_code=301)


@app.get("/{track_slug}/{race_date}", response_class=HTMLResponse)
async def public_curated_card_page(request: Request, track_slug: str, race_date: str):
    """Canonical public full-card route."""
    track_id = get_track_id_from_slug(track_slug)
    if not track_id or not _is_valid_race_date(race_date):
        return templates.TemplateResponse(
            request,
            "error.html",
            _template_context(request, "Card Not Found", error="The requested card could not be found."),
            status_code=404,
        )

    context = await _build_public_card_context(
        request,
        track_id=track_id,
        race_date=race_date,
        view_mode="full-card",
    )
    if not context:
        return templates.TemplateResponse(
            request,
            "error.html",
            _template_context(
                request,
                "Card Not Found",
                error=f"No published curated card found for {SUPPORTED_TRACKS.get(track_id, track_id)} on {race_date}.",
            ),
            status_code=404,
        )

    return templates.TemplateResponse(request, "curated_card.html", context)


@app.get("/{track_slug}/{race_date}/race-{race_number}", response_class=HTMLResponse)
async def public_curated_race_page(request: Request, track_slug: str, race_date: str, race_number: int):
    """Canonical public single-race route."""
    track_id = get_track_id_from_slug(track_slug)
    if not track_id or not _is_valid_race_date(race_date) or race_number <= 0:
        return templates.TemplateResponse(
            request,
            "error.html",
            _template_context(request, "Race Not Found", error="The requested race page could not be found."),
            status_code=404,
        )

    context = await _build_public_card_context(
        request,
        track_id=track_id,
        race_date=race_date,
        view_mode="race",
        selected_race_number=race_number,
    )
    if not context:
        return templates.TemplateResponse(
            request,
            "error.html",
            _template_context(
                request,
                "Race Not Found",
                error=f"No published curated card found for {SUPPORTED_TRACKS.get(track_id, track_id)} on {race_date}.",
            ),
            status_code=404,
        )
    if context.get("error") == "race_not_found":
        return templates.TemplateResponse(
            request,
            "error.html",
            _template_context(
                request,
                "Race Not Found",
                error=f"Race {race_number} is not available for {SUPPORTED_TRACKS.get(track_id, track_id)} on {race_date}.",
            ),
            status_code=404,
        )

    return templates.TemplateResponse(request, "curated_card.html", context)


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


def _apply_speed_figure_adjustment(
    predictions: List[Dict],
    dd_by_name: Dict,
) -> List[Dict]:
    """Bayesian blend of LLM composite_rating with normalized speed figures from deep-dive.

    Formula: new_rating = 0.70 × llm_rating + 0.30 × normalized_speed_figure
    Speed figure normalization: maps Beyer/speed fig range (55–120) onto 0–100 scale.
    Only adjusts horses where at least one speed figure is available in recent_results.
    Re-sorts predictions and recomputes softmax win_probability after adjustment.
    """
    predictions = [copy.deepcopy(p) for p in predictions]
    for pred in predictions:
        name = (pred.get("horse_name") or "").lower()
        dd_horse = dd_by_name.get(name, {})
        recent_results = dd_horse.get("recent_results", [])

        # Extract numeric speed figures from recent results (last 4)
        speed_figs: List[float] = []
        for r in recent_results[:4]:
            raw = r.get("speed_figure") or r.get("beyer") or r.get("fig") or 0
            try:
                val = float(raw)
                if val > 0:
                    speed_figs.append(val)
            except (TypeError, ValueError):
                pass

        if not speed_figs:
            continue  # No speed data available — do not adjust

        # Weighted average (most recent = highest weight)
        weights = [1.0, 0.8, 0.6, 0.4][: len(speed_figs)]
        weighted_avg = sum(f * w for f, w in zip(speed_figs, weights)) / sum(weights)

        # Normalize to 0–100 (Beyer 55 → 0, Beyer 120 → 100)
        normalized_speed = min(100.0, max(0.0, (weighted_avg - 55.0) * (100.0 / 65.0)))

        # Bayesian blend
        llm_rating = pred.get("composite_rating", 50.0)
        pred["composite_rating"] = round(0.70 * llm_rating + 0.30 * normalized_speed, 1)
        pred["_speed_figure_used"] = round(weighted_avg, 1)  # Diagnostic field

    # Re-sort by adjusted composite_rating
    predictions.sort(key=lambda x: x.get("composite_rating", 0), reverse=True)

    # Recompute softmax win_probability after adjustment
    import math as _math
    _T = 15.0
    _scores = [_math.exp(p.get("composite_rating", 0) / _T) for p in predictions]
    _total = sum(_scores) or 1.0
    for p, s in zip(predictions, _scores):
        p["win_probability"] = round((s / _total) * 100, 1)

    return predictions


def _build_admin_structuring_prompt(
    request: AdminRaceCardRequest,
    *,
    expected_race_numbers: Optional[List[int]] = None,
    missing_race_numbers: Optional[List[int]] = None,
    expected_horses_by_race: Optional[Dict[int, List[str]]] = None,
    missing_horses_by_race: Optional[Dict[int, List[str]]] = None,
    official_card_url: Optional[str] = None,
    per_race_urls: Optional[Dict[int, Dict[str, str]]] = None,
    equibase_entry_details: Optional[Dict[int, list]] = None,
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
    official_field_summary = _format_expected_field_summary(expected_horses_by_race, equibase_entry_details)

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
- `composite_rating` must be numeric on a 0-100 scale. Apply these spread rules strictly:
  * Anchor ratings to morning_line_odds and speed data. Cross-reference: a 2-1 morning line (~33% implied win prob) should score >=20 points above a 20-1 longshot (~5% implied win prob).
  * Heavy favorites (morning line <=2-1) must score >=80. Even-money horses must score >=85.
  * Longshots (morning line >=15-1) must score <=55. Horses at 20-1 or greater must score <=45.
  * The top-rated horse and the bottom-rated horse in any race must be separated by at least 25 points.
  * The top 3 horses must span at least 15 rating points.
  * Do NOT assign all horses ratings within 5 points of each other. Compress ratings only when the field is genuinely even — and in that case, keep the range between 50 and 70, not 80 to 90.
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


def _format_expected_field_summary(
    expected_horses_by_race: Dict[int, List[str]],
    equibase_entry_details: Optional[Dict[int, list]] = None,
) -> str:
    if not expected_horses_by_race:
        return ""

    entry_details = equibase_entry_details or {}
    race_summaries = []
    for race_number in sorted(expected_horses_by_race):
        horse_names = expected_horses_by_race[race_number]
        if not horse_names:
            continue

        # If we have detailed entry data for this race, include PP/jockey/trainer
        race_entries = entry_details.get(race_number, [])
        if race_entries:
            entry_strs = []
            for entry in race_entries:
                if entry.get("scratched"):
                    continue
                parts = [entry.get("name", "?")]
                if entry.get("post_position"):
                    parts[0] = f"PP{entry['post_position']}-{parts[0]}"
                if entry.get("jockey"):
                    parts.append(f"J:{entry['jockey']}")
                if entry.get("trainer"):
                    parts.append(f"T:{entry['trainer']}")
                entry_strs.append(" ".join(parts))
            if entry_strs:
                race_summaries.append(f"Race {race_number} ({len(entry_strs)} runners): {'; '.join(entry_strs)}")
                continue

        # Fallback: just horse names
        race_summaries.append(f"Race {race_number} ({len(horse_names)}): {', '.join(horse_names)}")

    if not race_summaries:
        return ""
    return (
        "Official horse fields by race (use these EXACT post positions, jockeys, and trainers): "
        + " | ".join(race_summaries)
    )


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
    equibase_entry_details: Optional[Dict[int, list]] = None,
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

    # Build Equibase-sourced hints for the incomplete races
    equibase_hints = ""
    entry_details = equibase_entry_details or {}
    if entry_details:
        hint_lines = []
        for rn in sorted(incomplete_field_races):
            entries = entry_details.get(rn, [])
            if entries:
                entry_strs = []
                for e in entries:
                    if e.get("scratched"):
                        continue
                    parts = [e.get("name", "?")]
                    if e.get("jockey"):
                        parts.append(f"J:{e['jockey']}")
                    if e.get("trainer"):
                        parts.append(f"T:{e['trainer']}")
                    entry_strs.append(" ".join(parts))
                if entry_strs:
                    hint_lines.append(f"  Race {rn}: {'; '.join(entry_strs)}")
        if hint_lines:
            equibase_hints = (
                "\nIMPORTANT — We already parsed these jockey/trainer values from Equibase. "
                "Use these as authoritative data:\n" + "\n".join(hint_lines)
            )

    return f"""
You are filling in missing jockey and trainer data for a horse racing card.

Track: {SUPPORTED_TRACKS[request.track_id]} ({request.track_id})
Country: {track_country}
Race date: {request.race_date}

{search_instruction}
{url_block}
{equibase_hints}

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

# ── Automation scheduler instance ─────────────────────────────────────────────
# AUTOMATION_TRACKS controls which tracks are automated (comma-separated IDs).
# If unset or empty, automation is disabled for all tracks.
# Example: AUTOMATION_TRACKS=DMR        → only Del Mar
#          AUTOMATION_TRACKS=DMR,SA     → Del Mar and Santa Anita
_AUTOMATION_TRACK_IDS = [
    tid.strip().upper()
    for tid in os.getenv("AUTOMATION_TRACKS", "").split(",")
    if tid.strip()
]
_AUTOMATION_TRACKS_FULL = {
    tid: cfg for tid, cfg in TRACK_CONFIG_FULL.items() if tid in _AUTOMATION_TRACK_IDS
}
if _AUTOMATION_TRACK_IDS:
    unknown = set(_AUTOMATION_TRACK_IDS) - set(TRACK_CONFIG_FULL)
    if unknown:
        logger.warning("AUTOMATION_TRACKS contains unknown track IDs: %s", unknown)
    logger.info("Automation enabled for tracks: %s", list(_AUTOMATION_TRACKS_FULL.keys()))
else:
    logger.info("Automation disabled — AUTOMATION_TRACKS not set")

try:
    from services.automation_scheduler import AutomationScheduler
    _automation_scheduler = AutomationScheduler(tracks=_AUTOMATION_TRACKS_FULL) if _AUTOMATION_TRACKS_FULL else None
except Exception as _sched_err:
    logger.warning("Could not import AutomationScheduler: %s", _sched_err)
    _automation_scheduler = None  # type: ignore[assignment]


# Application lifecycle events
@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    logger.info(f"Starting {BRAND_NAME}")
    await app_state.initialize()

    # Auto-purge expired curated cards on startup
    try:
        sm = await app_state.ensure_session_manager()
        if sm:
            purged = await sm.purge_expired_curated_cards(retention_days=CARD_RETENTION_DAYS)
            if purged:
                logger.info("🗑️ Startup purge: removed %d expired cards (retention=%d days)", purged, CARD_RETENTION_DAYS)
    except Exception as e:
        logger.warning("Startup card purge failed (non-fatal): %s", e)

    # Start the automation scheduler
    if _automation_scheduler is not None:
        try:
            _automation_scheduler.start()
        except Exception as e:
            logger.warning("Automation scheduler failed to start (non-fatal): %s", e)

    logger.info("Application startup complete")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown"""
    logger.info(f"Shutting down {BRAND_NAME}")

    # Stop the automation scheduler
    if _automation_scheduler is not None:
        try:
            await _automation_scheduler.stop()
        except Exception as e:
            logger.warning("Automation scheduler stop failed: %s", e)

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

    if uvicorn is None:
        raise RuntimeError(
            "uvicorn is required to run app.py directly. Install uvicorn or start the app with your ASGI server."
        )

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
