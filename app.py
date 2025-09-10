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
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import uvicorn
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import existing components
from race_prediction_engine import RacePredictionEngine
from scrapers.playwright_equibase_scraper import PlaywrightEquibaseScraper
from scrapers.smartpick_scraper import SmartPickRaceScraper
from config.config_manager import ConfigManager

# Import new services (to be created)
try:
    from services.session_manager import SessionManager
    from services.orchestration_service import OrchestrationService
    from services.openrouter_client import OpenRouterClient
except ImportError:
    # Services not yet created - will be implemented
    SessionManager = None
    OrchestrationService = None
    OpenRouterClient = None

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

# Initialize FastAPI app
app = FastAPI(
    title="Del Mar Race Analysis Application",
    description="AI-Powered Horse Racing Scraper, Analyzer & Prediction Platform",
    version="1.0.0"
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
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
        
    async def initialize(self):
        """Initialize services that require async setup"""
        try:
            if SessionManager:
                self.session_manager = SessionManager()
                await self.session_manager.initialize()
            
            if OrchestrationService:
                self.orchestration_service = OrchestrationService(
                    session_manager=self.session_manager,
                    prediction_engine=self.prediction_engine,
                    config_manager=self.config_manager
                )
            
            if OpenRouterClient:
                self.openrouter_client = OpenRouterClient(self.config)
                
            logger.info("Application state initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize application state: {e}")

# Global app state instance
app_state = AppState()

# Pydantic models for API requests
class AnalysisRequest(BaseModel):
    date: str  # Format: YYYY-MM-DD
    llm_model: str = "gpt-4o"
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
    """Main landing page with date and model selection"""
    return templates.TemplateResponse("landing.html", {
        "request": request,
        "title": "Del Mar Race Analysis",
        "available_models": [
            "gpt-4o",
            "gpt-4-turbo", 
            "claude-3-sonnet",
            "claude-3-haiku"
        ],
        "default_date": datetime.now().strftime("%Y-%m-%d")
    })

@app.post("/api/analyze")
async def start_analysis(request: AnalysisRequest, background_tasks: BackgroundTasks):
    """Start race analysis for specified date"""
    try:
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
        
        # Start background analysis task
        background_tasks.add_task(
            run_analysis_pipeline,
            session_id=session_id,
            date=request.date,
            llm_model=request.llm_model,
            track_id=request.track_id
        )
        
        return JSONResponse({
            "session_id": session_id,
            "status": "started",
            "message": f"Analysis started for {request.date}"
        })
        
    except Exception as e:
        logger.error(f"Failed to start analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/status/{session_id}")
async def get_analysis_status(session_id: str):
    """Get current status of analysis session"""
    try:
        if app_state.session_manager:
            status = await app_state.session_manager.get_session_status(session_id)
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
    except Exception as e:
        logger.error(f"Failed to get status for session {session_id}: {e}")
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
    return JSONResponse({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "session_manager": app_state.session_manager is not None,
            "orchestration_service": app_state.orchestration_service is not None,
            "openrouter_client": app_state.openrouter_client is not None,
            "prediction_engine": app_state.prediction_engine is not None
        }
    })

# Background task functions
async def run_analysis_pipeline(session_id: str, date: str, llm_model: str, track_id: str):
    """Background task to run the complete analysis pipeline"""
    try:
        logger.info(f"Starting analysis pipeline for session {session_id}")
        
        # Update session status
        if app_state.session_manager:
            await app_state.session_manager.update_session_status(
                session_id, "running", 10, "Initializing scraping", "Setting up scrapers..."
            )
        
        # Step 1: Initialize scrapers
        playwright_scraper = None
        smartpick_scraper = None
        
        try:
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
                
    except Exception as e:
        logger.error(f"Critical error in analysis pipeline for session {session_id}: {e}")

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

    # Run development/production server
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        reload=bool(os.environ.get("RELOAD", False)),
        log_level=os.environ.get("LOG_LEVEL", "info").lower()
    )
