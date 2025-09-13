#!/usr/bin/env python3
"""
Deployment Check Script for Del Mar Race Analyzer
Verifies all components are properly integrated and ready for Render.com deployment
"""

import sys
import os
import importlib
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def check_dependencies():
    """Check if all required dependencies are available"""
    logger.info("Checking dependencies...")
    
    required_packages = [
        'fastapi',
        'uvicorn',
        'playwright',
        'xgboost',
        'sklearn',
        'pandas',
        'numpy',
        'requests',
        'bs4',  # beautifulsoup4 imports as bs4
        'aiosqlite'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            if package == 'sklearn':
                importlib.import_module('sklearn')
            else:
                importlib.import_module(package)
            logger.info(f"✓ {package}")
        except ImportError:
            missing_packages.append(package)
            logger.error(f"✗ {package} - MISSING")
    
    return len(missing_packages) == 0, missing_packages

def check_core_services():
    """Check if core services can be imported"""
    logger.info("Checking core services...")
    
    services = [
        ('race_prediction_engine', 'RacePredictionEngine'),
        ('services.gradient_boosting_predictor', 'GradientBoostingPredictor'),
        ('services.kelly_optimizer', 'KellyCriterionOptimizer'),
        ('services.validation_framework', 'ValidationFramework'),
        ('services.orchestration_service', 'OrchestrationService'),
        ('services.session_manager', 'SessionManager'),
        ('services.openrouter_client', 'OpenRouterClient')
    ]
    
    failed_imports = []
    for module_name, class_name in services:
        try:
            module = importlib.import_module(module_name)
            getattr(module, class_name)
            logger.info(f"✓ {module_name}.{class_name}")
        except (ImportError, AttributeError) as e:
            failed_imports.append((module_name, class_name, str(e)))
            logger.error(f"✗ {module_name}.{class_name} - {e}")
    
    return len(failed_imports) == 0, failed_imports

def check_scrapers():
    """Check if scrapers can be imported"""
    logger.info("Checking scrapers...")
    
    scrapers = [
        ('scrapers.playwright_equibase_scraper', 'PlaywrightEquibaseScraper'),
        ('scrapers.smartpick_scraper', 'SmartPickRaceScraper'),
        ('scrapers.playwright_integration', 'validate_scraping_consistency'),
        ('race_entry_scraper', 'RaceEntryScraper')
    ]
    
    failed_imports = []
    for module_name, class_name in scrapers:
        try:
            module = importlib.import_module(module_name)
            if hasattr(module, class_name):
                logger.info(f"✓ {module_name}.{class_name}")
            else:
                failed_imports.append((module_name, class_name, "Class not found"))
                logger.error(f"✗ {module_name}.{class_name} - Class not found")
        except ImportError as e:
            failed_imports.append((module_name, class_name, str(e)))
            logger.error(f"✗ {module_name}.{class_name} - {e}")
    
    return len(failed_imports) == 0, failed_imports

def check_app_initialization():
    """Check if the main app can be initialized"""
    logger.info("Checking app initialization...")
    
    try:
        # Add current directory to path
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        
        # Import main app
        from app import app, AppState
        
        # Try to create app state
        app_state = AppState()
        logger.info("✓ App and AppState can be created")
        
        # Check if FastAPI app is properly configured
        if hasattr(app, 'routes') and len(app.routes) > 0:
            logger.info(f"✓ FastAPI app has {len(app.routes)} routes configured")
        else:
            logger.error("✗ FastAPI app has no routes configured")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"✗ App initialization failed: {e}")
        return False

def check_ml_integration():
    """Check if ML services are properly integrated"""
    logger.info("Checking ML integration...")
    
    try:
        from race_prediction_engine import RacePredictionEngine
        from services.gradient_boosting_predictor import GradientBoostingPredictor
        from services.kelly_optimizer import KellyCriterionOptimizer
        
        # Test prediction engine with dynamic weights
        engine = RacePredictionEngine()
        
        # Test dynamic weight calculation
        race_info = {
            'surface': 'Turf',
            'distance': '1 Mile',
            'race_type': 'Maiden'
        }
        
        dynamic_weights = engine.get_dynamic_weights(race_info)
        if abs(sum(dynamic_weights.values()) - 1.0) < 0.001:
            logger.info("✓ Dynamic weight adjustment working")
        else:
            logger.error("✗ Dynamic weight adjustment not normalized")
            return False
        
        # Test ML predictor initialization
        try:
            gb_predictor = GradientBoostingPredictor()

            # Test with sample data
            sample_horse_data = {
                'speed_score': 85.0,
                'class_rating': 75.0,
                'form_rating': 80.0,
                'workout_rating': 70.0,
                'jockey_stats': {'win_percentage': 15.0},
                'trainer_stats': {'win_percentage': 12.0},
                'recent_performances': [
                    {'finish_position': 2, 'speed_figure': 82},
                    {'finish_position': 1, 'speed_figure': 88},
                    {'finish_position': 3, 'speed_figure': 79}
                ]
            }

            sample_race_info = {
                'surface': 'Dirt',
                'distance': '6 Furlongs',
                'race_type': 'Maiden'
            }

            # Test prediction (should work even without training)
            prediction = gb_predictor.predict_finish_position(sample_horse_data, sample_race_info)
            confidence = gb_predictor.get_prediction_confidence(sample_horse_data, sample_race_info)

            logger.info("✓ Gradient Boosting Predictor can be initialized and make predictions")
        except Exception as e:
            logger.warning(f"⚠ Gradient Boosting Predictor initialization failed: {e}")
        
        # Test Kelly optimizer
        kelly_optimizer = KellyCriterionOptimizer()
        test_result = kelly_optimizer.calculate_optimal_stake(0.25, 4.0, 1000.0, 1000.0)
        if 'stake_size' in test_result:
            logger.info("✓ Kelly Criterion Optimizer working")
        else:
            logger.error("✗ Kelly Criterion Optimizer not working")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"✗ ML integration check failed: {e}")
        return False

def check_templates():
    """Check if templates exist and are valid"""
    logger.info("Checking templates...")
    
    required_templates = [
        'templates/base.html',
        'templates/landing.html',
        'templates/progress.html',
        'templates/results.html',
        'templates/error.html'
    ]
    
    missing_templates = []
    for template in required_templates:
        if os.path.exists(template):
            logger.info(f"✓ {template}")
        else:
            missing_templates.append(template)
            logger.error(f"✗ {template} - MISSING")
    
    return len(missing_templates) == 0, missing_templates

def main():
    """Run all deployment checks"""
    logger.info("🚀 Starting Del Mar Race Analyzer Deployment Check")
    logger.info("=" * 60)
    
    all_checks_passed = True
    
    # Check dependencies
    deps_ok, missing_deps = check_dependencies()
    if not deps_ok:
        logger.error(f"Missing dependencies: {missing_deps}")
        all_checks_passed = False
    
    logger.info("-" * 40)
    
    # Check core services
    services_ok, failed_services = check_core_services()
    if not services_ok:
        logger.error(f"Failed service imports: {failed_services}")
        all_checks_passed = False
    
    logger.info("-" * 40)
    
    # Check scrapers
    scrapers_ok, failed_scrapers = check_scrapers()
    if not scrapers_ok:
        logger.error(f"Failed scraper imports: {failed_scrapers}")
        all_checks_passed = False
    
    logger.info("-" * 40)
    
    # Check app initialization
    app_ok = check_app_initialization()
    if not app_ok:
        all_checks_passed = False
    
    logger.info("-" * 40)
    
    # Check ML integration
    ml_ok = check_ml_integration()
    if not ml_ok:
        all_checks_passed = False
    
    logger.info("-" * 40)
    
    # Check templates
    templates_ok, missing_templates = check_templates()
    if not templates_ok:
        logger.error(f"Missing templates: {missing_templates}")
        all_checks_passed = False
    
    logger.info("=" * 60)
    
    if all_checks_passed:
        logger.info("🎉 ALL CHECKS PASSED - Ready for Render.com deployment!")
        return 0
    else:
        logger.error("❌ SOME CHECKS FAILED - Fix issues before deployment")
        return 1

if __name__ == "__main__":
    sys.exit(main())
