#!/usr/bin/env python3
"""
Del Mar Race Analysis Application
Main FastAPI application entry point

Transforms existing horse racing analysis tools into a unified web application
with AI-powered enhancements and professional user interface.
"""

import asyncio
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import uvicorn
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
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
    from services.orchestration_service import OrchestrationService
    from services.openrouter_client import OpenRouterClient
    from services.gradient_boosting_predictor import GradientBoostingPredictor
    from services.kelly_optimizer import KellyCriterionOptimizer
    from services.race_card_admin import extract_json_object, normalize_admin_results
except ImportError as e:
    print(f"Some services not available: {e}")
    SessionManager = None
    OrchestrationService = None
    OpenRouterClient = None
    GradientBoostingPredictor = None
    KellyCriterionOptimizer = None
    extract_json_object = None
    normalize_admin_results = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

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
        
    async def initialize(self):
        """Initialize services that require async setup"""
        try:
            if SessionManager:
                self.session_manager = SessionManager(config=self.config)
                await self.session_manager.initialize()

                # Recover any interrupted sessions from previous restart
                await self.session_manager.recover_interrupted_sessions()

            if OrchestrationService:
                self.orchestration_service = OrchestrationService(
                    session_manager=self.session_manager,
                    prediction_engine=self.prediction_engine,
                    config_manager=self.config_manager
                )
            
            if OpenRouterClient:
                self.openrouter_client = OpenRouterClient(self.config)

            # Initialize ML services
            if GradientBoostingPredictor:
                try:
                    self.gradient_boosting_predictor = GradientBoostingPredictor()
                    logger.info("Gradient Boosting Predictor initialized")
                except Exception as e:
                    logger.warning(f"Failed to initialize Gradient Boosting Predictor: {e}")

            if KellyCriterionOptimizer:
                self.kelly_optimizer = KellyCriterionOptimizer()
                logger.info("Kelly Criterion Optimizer initialized")

            logger.info("Application state initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize application state: {e}")

# Global app state instance
app_state = AppState()

# Supported tracks
SUPPORTED_TRACKS = {
    "DMR": "Del Mar",
    "SA": "Santa Anita"
}

MODEL_OPTIONS = [
    {
        "id": "google/gemini-3.1-flash-lite-preview",
        "label": "Gemini 3.1 Flash Lite Preview",
        "tier_label": "Cheap",
        "description": "Fast, lower-cost option for first-pass structuring.",
    },
    {
        "id": "x-ai/grok-4.20-beta",
        "label": "Grok 4.20 Beta",
        "tier_label": "Affordable",
        "description": "Balanced option for race-card organization and ranking.",
    },
    {
        "id": "openai/gpt-5.4",
        "label": "GPT-5.4",
        "tier_label": "Best",
        "description": "Highest-quality option for the strongest reasoning pass.",
    },
]
MODEL_LOOKUP = {model["id"]: model for model in MODEL_OPTIONS}
DEFAULT_LLM_MODEL = "x-ai/grok-4.20-beta"
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
    llm_model: str = DEFAULT_LLM_MODEL
    track_id: str = "DMR"  # DMR (Del Mar) or SA (Santa Anita)


class AdminRaceCardRequest(BaseModel):
    race_date: str
    track_id: str = "DMR"
    llm_model: str = DEFAULT_LLM_MODEL
    source_text: str
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
    dashboard_cards = await _load_dashboard_cards(limit=8)
    return templates.TemplateResponse("landing.html", {
        "request": request,
        "title": "Race Card Dashboard",
        "dashboard_cards": dashboard_cards,
        "card_count": len(dashboard_cards),
        "completed_count": len([card for card in dashboard_cards if card["status"] == "completed"]),
        "openrouter_configured": bool(app_state.openrouter_client and app_state.openrouter_client.api_key),
    })


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    """Admin workflow for saving structured race cards with OpenRouter."""
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "title": "Admin Race Card Workflow",
        "model_options": MODEL_OPTIONS,
        "default_model": DEFAULT_LLM_MODEL,
        "available_tracks": [{"id": track_id, "name": track_name} for track_id, track_name in SUPPORTED_TRACKS.items()],
        "default_date": datetime.now().strftime("%Y-%m-%d"),
        "openrouter_configured": bool(app_state.openrouter_client and app_state.openrouter_client.api_key),
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

        # Create new analysis session
        if app_state.session_manager:
            session_id = await app_state.session_manager.create_session(
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
async def create_admin_race_card(request: AdminRaceCardRequest):
    """Create a saved race card from pasted source material using OpenRouter."""
    if not app_state.session_manager:
        raise HTTPException(status_code=503, detail="Session manager is not available")
    if not app_state.openrouter_client or not app_state.openrouter_client.api_key:
        raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY is not configured on the server")
    if not extract_json_object or not normalize_admin_results:
        raise HTTPException(status_code=503, detail="Admin race-card helpers are unavailable")

    _validate_track_id(request.track_id)
    _validate_llm_model(request.llm_model)

    try:
        datetime.strptime(request.race_date, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD") from exc

    source_text = request.source_text.strip()
    if not source_text:
        raise HTTPException(status_code=400, detail="Source text is required")

    started_at = time.perf_counter()
    session_id = await app_state.session_manager.create_session(
        race_date=request.race_date,
        llm_model=request.llm_model,
        track_id=request.track_id,
    )

    try:
        await app_state.session_manager.update_session_status(
            session_id, "running", 25, "admin_structuring", "Structuring race card with OpenRouter"
        )

        raw_response = await app_state.openrouter_client.call_model(
            model=request.llm_model,
            task_type="analysis",
            prompt=_build_admin_structuring_prompt(request),
            context={
                "race_date": request.race_date,
                "track_id": request.track_id,
                "track_name": SUPPORTED_TRACKS[request.track_id],
                "source_urls": request.source_urls,
                "admin_notes": request.admin_notes,
                "source_text": source_text,
            },
            max_tokens=2500,
            temperature=0.2,
        )
        structured_payload = extract_json_object(raw_response)
        normalized_results = normalize_admin_results(
            structured_payload,
            race_date=request.race_date,
            track_id=request.track_id,
            llm_model=request.llm_model,
            source_urls=request.source_urls,
            admin_notes=request.admin_notes,
            analysis_duration_seconds=time.perf_counter() - started_at,
        )

        await app_state.session_manager.save_session_results(session_id, normalized_results)
        await app_state.session_manager.update_session_status(
            session_id, "completed", 100, "analysis_complete", "Admin race card saved"
        )

        return JSONResponse({
            "session_id": session_id,
            "status": "completed",
            "redirect_url": f"/results/{session_id}",
        })
    except ValueError as exc:
        await app_state.session_manager.update_session_status(
            session_id, "failed", 0, "admin_failed", str(exc)
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        await app_state.session_manager.update_session_status(
            session_id, "failed", 0, "admin_failed", "Admin race card creation failed"
        )
        raise
    except Exception as exc:
        logger.error(f"Admin race card creation failed: {exc}")
        await app_state.session_manager.update_session_status(
            session_id, "failed", 0, "admin_failed", str(exc)
        )
        raise HTTPException(status_code=500, detail=f"Failed to create admin race card: {exc}") from exc

@app.get("/api/status/{session_id}")
async def get_analysis_status(session_id: str):
    """Get current status of analysis session"""
    try:
        if app_state.session_manager:
            status = await app_state.session_manager.get_session_status(session_id)

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
        if app_state.session_manager:
            await app_state.session_manager.update_session_status(
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
        if app_state.session_manager:
            results = await app_state.session_manager.get_session_results(session_id)
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
    if llm_model not in MODEL_LOOKUP:
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


def _build_admin_structuring_prompt(request: AdminRaceCardRequest) -> str:
    return f"""
You are structuring a horse racing card for internal display.

Track: {SUPPORTED_TRACKS[request.track_id]} ({request.track_id})
Race date: {request.race_date}

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
- Include every race you can identify from the provided source material.
- Order each race's predictions strongest to weakest.
- Use only grounded details from the supplied material; leave uncertain text blank instead of inventing facts.
- `composite_rating` must be numeric on a 0-100 scale.
- Keep notes concise.
""".strip()

@app.post("/api/validate")
async def run_validation():
    """Run validation framework to test prediction accuracy"""
    try:
        if not app_state.orchestration_service or not app_state.orchestration_service.validation_framework:
            raise HTTPException(status_code=503, detail="Validation framework not available")

        # Run backtest validation
        validation_result = app_state.orchestration_service.validation_framework.run_backtest(
            app_state.prediction_engine
        )

        # Generate comprehensive report
        validation_report = app_state.orchestration_service.validation_framework.generate_validation_report(
            validation_result
        )

        return {
            "status": "success",
            "validation_report": validation_report,
            "timestamp": datetime.now().isoformat()
        }

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
