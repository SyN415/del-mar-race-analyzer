#!/usr/bin/env python3
"""
Orchestration Service
Coordinates the complete analysis workflow using existing components
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Import scrapers with fallback handling
try:
    from scrapers.playwright_equibase_scraper import PlaywrightEquibaseScraper
    # Use the fixed Playwright-based SmartPick scraper that handles Angular/JavaScript rendering
    try:
        from scrapers.smartpick_playwright import FixedPlaywrightSmartPickScraper as SmartPickRaceScraper
        logger.info("✅ Using fixed Playwright SmartPick scraper with Angular support")
    except ImportError:
        from scrapers.smartpick_scraper import SmartPickRaceScraper
        logger.warning("⚠️  Using fallback SmartPick scraper (may not work with Angular pages)")
    PLAYWRIGHT_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Playwright scrapers not available: {e}")
    from scrapers.fallback_scraper import FallbackEquibaseScraper, FallbackSmartPickScraper
    PlaywrightEquibaseScraper = FallbackEquibaseScraper
    SmartPickRaceScraper = FallbackSmartPickScraper
    PLAYWRIGHT_AVAILABLE = False
from race_prediction_engine import RacePredictionEngine
from services.session_manager import SessionManager
from services.openrouter_client import OpenRouterClient
from services.ai_scraping_assistant import AIScrapingAssistant
from services.ai_analysis_enhancer import AIAnalysisEnhancer

# Import new ML services with fallback handling
try:
    from services.gradient_boosting_predictor import GradientBoostingPredictor
    from services.kelly_optimizer import KellyCriterionOptimizer
    from services.validation_framework import ValidationFramework
    from scrapers.playwright_integration import validate_scraping_consistency
    ML_SERVICES_AVAILABLE = True
except ImportError as e:
    logger.warning(f"ML services not available: {e}")
    GradientBoostingPredictor = None
    KellyCriterionOptimizer = None
    ValidationFramework = None
    validate_scraping_consistency = None
    ML_SERVICES_AVAILABLE = False

logger = logging.getLogger(__name__)

class OrchestrationService:
    """Orchestrates the complete race analysis workflow with AI enhancement"""

    def __init__(self, session_manager: SessionManager, prediction_engine: RacePredictionEngine,
                 config_manager=None):
        self.session_manager = session_manager
        self.prediction_engine = prediction_engine
        self.config_manager = config_manager

        # Initialize AI services
        self.ai_client = OpenRouterClient(config_manager) if config_manager else None
        self.ai_scraping_assistant = AIScrapingAssistant(self.ai_client) if self.ai_client else None
        self.ai_analysis_enhancer = AIAnalysisEnhancer(self.ai_client) if self.ai_client else None

        # Initialize ML services
        self.gradient_boosting_predictor = None
        self.kelly_optimizer = None
        self.validation_framework = None

        if ML_SERVICES_AVAILABLE:
            try:
                if GradientBoostingPredictor:
                    self.gradient_boosting_predictor = GradientBoostingPredictor()
                    logger.info("Gradient Boosting Predictor initialized in orchestration")
                if KellyCriterionOptimizer:
                    self.kelly_optimizer = KellyCriterionOptimizer()
                    logger.info("Kelly Criterion Optimizer initialized in orchestration")
                if ValidationFramework:
                    self.validation_framework = ValidationFramework()
                    logger.info("Validation Framework initialized in orchestration")
            except Exception as e:
                logger.warning(f"Failed to initialize ML services: {e}")
        
    async def analyze_race_card(self, session_id: str, race_date: str, track_id: str = "DMR") -> Dict:
        """
        Complete race card analysis workflow
        
        Args:
            session_id: Session identifier
            race_date: Race date in YYYY-MM-DD format
            track_id: Track identifier (default: DMR for Del Mar)
            
        Returns:
            Complete analysis results
        """
        start_time = datetime.now()
        
        try:
            # Step 1: Update status - Starting analysis
            await self.session_manager.update_session_status(
                session_id, "running", 5, "initializing", "Starting race card analysis..."
            )
            
            # Step 2: Load or scrape race card overview
            race_card = await self._get_race_card_overview(session_id, race_date, track_id)
            if not race_card or not race_card.get('races'):
                raise Exception("Failed to load race card data")
            
            await self.session_manager.update_session_status(
                session_id, "running", 15, "race_card_loaded", 
                f"Loaded {len(race_card['races'])} races"
            )
            
            # Step 3: Scrape horse data for all races
            all_horse_data = await self._scrape_all_horse_data(session_id, race_card, race_date)
            
            await self.session_manager.update_session_status(
                session_id, "running", 60, "horse_data_scraped", 
                f"Scraped data for {len(all_horse_data)} horses"
            )
            
            # Step 4: Enhance with SmartPick data
            enhanced_horse_data = await self._enhance_with_smartpick_data(
                session_id, race_card, all_horse_data, race_date, track_id
            )
            
            await self.session_manager.update_session_status(
                session_id, "running", 80, "smartpick_enhanced", 
                "Enhanced with SmartPick jockey/trainer data"
            )
            
            # Step 5: Run predictions for all races
            race_analyses = await self._analyze_all_races(
                session_id, race_card, enhanced_horse_data
            )
            
            await self.session_manager.update_session_status(
                session_id, "running", 95, "predictions_complete", 
                f"Generated predictions for {len(race_analyses)} races"
            )
            
            # Step 6: Generate enhanced summary with AI recommendations
            summary = await self._generate_analysis_summary(race_analyses, session_id)

            # Step 7: Compile final results
            analysis_duration = (datetime.now() - start_time).total_seconds()

            final_results = {
                "session_id": session_id,
                "race_date": race_date,
                "track_id": track_id,
                "analysis_duration_seconds": analysis_duration,
                "total_races": len(race_card['races']),
                "total_horses": len(enhanced_horse_data),
                "race_card": race_card,
                "horse_data": enhanced_horse_data,
                "race_analyses": race_analyses,
                "generated_at": datetime.now().isoformat(),
                "summary": summary,
                "ai_services_used": {
                    "openrouter_client": self.ai_client is not None,
                    "scraping_assistant": self.ai_scraping_assistant is not None,
                    "analysis_enhancer": self.ai_analysis_enhancer is not None
                }
            }
            
            # Step 8: Save results and update final status
            await self.session_manager.save_session_results(session_id, final_results)
            await self.session_manager.update_session_status(
                session_id, "completed", 100, "analysis_complete",
                f"Analysis completed in {analysis_duration:.1f} seconds with AI enhancement"
            )
            
            logger.info(f"Race card analysis completed for session {session_id}")
            return final_results
            
        except Exception as e:
            logger.error(f"Race card analysis failed for session {session_id}: {e}")
            await self.session_manager.update_session_status(
                session_id, "failed", 0, "analysis_failed", str(e)
            )
            raise
    
    async def _get_race_card_overview(self, session_id: str, race_date: str, track_id: str) -> Dict:
        """Get race card overview data"""
        try:
            # Import the existing race card loading logic
            from scrapers.playwright_integration import scrape_overview, convert_overview_to_race_card
            
            # Convert date format for scraping (MM/DD/YYYY)
            date_parts = race_date.split('-')  # YYYY-MM-DD
            scrape_date = f"{date_parts[1]}/{date_parts[2]}/{date_parts[0]}"
            
            # Scrape race card overview
            overview_result = await scrape_overview()
            if overview_result and overview_result.get('races'):
                race_card = convert_overview_to_race_card(overview_result, scrape_date)
                return race_card
            else:
                raise Exception("Failed to scrape race card overview")
                
        except Exception as e:
            logger.error(f"Failed to get race card overview: {e}")
            raise
    
    async def _scrape_all_horse_data(self, session_id: str, race_card: Dict, race_date: str) -> Dict:
        """Scrape detailed data for all horses in the race card"""
        all_horse_data = {}
        
        try:
            # Collect all horses with profile URLs
            horses_to_scrape = []
            for race in race_card.get('races', []):
                for horse in race.get('horses', []):
                    horse_name = horse.get('name', '')
                    profile_url = horse.get('profile_url', '')
                    if horse_name and profile_url:
                        horses_to_scrape.append((horse_name, profile_url))
            
            if not horses_to_scrape:
                logger.warning("No horses with profile URLs found")
                return all_horse_data
            
            # Check cache first
            cached_count = 0
            for horse_name, profile_url in horses_to_scrape:
                cached_data = await self.session_manager.get_cached_horse_data(race_date, horse_name)
                if cached_data:
                    all_horse_data[horse_name] = cached_data
                    cached_count += 1
            
            # Scrape remaining horses
            horses_to_scrape_fresh = [
                (name, url) for name, url in horses_to_scrape 
                if name not in all_horse_data
            ]
            
            if horses_to_scrape_fresh:
                logger.info(f"Scraping {len(horses_to_scrape_fresh)} horses (cached: {cached_count})")
                
                if PLAYWRIGHT_AVAILABLE:
                    async with PlaywrightEquibaseScraper() as scraper:
                        scraped_data = await scraper.scrape_multiple_horses(horses_to_scrape_fresh)
                else:
                    # Use fallback scraper
                    scraper = PlaywrightEquibaseScraper()  # Actually FallbackEquibaseScraper
                    scraped_data = await scraper.scrape_horse_data(horses_to_scrape_fresh)
                    
                    # Cache and merge scraped data with validation
                    for horse_name, horse_data in scraped_data.items():
                        # Apply scraping consistency validation if available
                        if validate_scraping_consistency:
                            horse_data = validate_scraping_consistency(horse_data)

                        all_horse_data[horse_name] = horse_data
                        await self.session_manager.cache_horse_data(
                            session_id, race_date, horse_name, horse_data
                        )
            
            logger.info(f"Collected data for {len(all_horse_data)} horses")
            return all_horse_data
            
        except Exception as e:
            logger.error(f"Failed to scrape horse data: {e}")
            raise
    
    async def _enhance_with_smartpick_data(self, session_id: str, race_card: Dict,
                                         horse_data: Dict, race_date: str, track_id: str) -> Dict:
        """Enhance horse data with SmartPick jockey/trainer information"""
        enhanced_data = horse_data.copy()

        try:
            # Convert date format for SmartPick (MM/DD/YYYY)
            date_parts = race_date.split('-')
            smartpick_date = f"{date_parts[1]}/{date_parts[2]}/{date_parts[0]}"

            # Use async context manager for Playwright-based scraper
            async with SmartPickRaceScraper() as smartpick_scraper:
                # Process each race
                for race in race_card.get('races', []):
                    race_number = race.get('race_number', 0)

                    if race_number > 0:
                        # Scrape SmartPick data for this race (await async method)
                        smartpick_data = await smartpick_scraper.scrape_race(
                            track_id, smartpick_date, race_number
                        )

                        # Merge SmartPick data with existing horse data
                        for horse_name, sp_data in smartpick_data.items():
                            if horse_name in enhanced_data:
                                # Merge SmartPick data
                                enhanced_data[horse_name]['smartpick'] = sp_data.get('smartpick', {})

                                # Update quality rating if SmartPick has better data
                                if sp_data.get('quality_rating', 0) > enhanced_data[horse_name].get('quality_rating', 0):
                                    enhanced_data[horse_name]['quality_rating'] = sp_data['quality_rating']

                                # Add OUR speed figure if available
                                if sp_data.get('our_speed_figure'):
                                    enhanced_data[horse_name]['our_speed_figure'] = sp_data['our_speed_figure']

            return enhanced_data

        except Exception as e:
            logger.error(f"Failed to enhance with SmartPick data: {e}")
            # Return original data if SmartPick enhancement fails
            return enhanced_data
    
    async def _analyze_all_races(self, session_id: str, race_card: Dict, horse_data: Dict) -> List[Dict]:
        """Run prediction analysis for all races with AI enhancement"""
        race_analyses = []

        try:
            total_races = len(race_card.get('races', []))

            for i, race in enumerate(race_card.get('races', [])):
                race_num = race.get('race_number', 0)

                # Update progress
                progress = 60 + (i / total_races * 30)  # 60-90% for race analysis
                await self.session_manager.update_session_status(
                    session_id, "running", progress, "analyzing",
                    f"Analyzing race {race_num}..."
                )

                try:
                    # Run basic prediction analysis
                    predictions = self.prediction_engine.predict_race(race, horse_data)

                    # Enhance with ML predictions if available
                    if self.gradient_boosting_predictor and predictions.get('predictions'):
                        try:
                            for horse_pred in predictions['predictions']:
                                horse_name = horse_pred.get('name', '')
                                if horse_name in horse_data:
                                    # Get ML prediction
                                    ml_prediction = self.gradient_boosting_predictor.predict_finish_position(
                                        horse_data[horse_name], race
                                    )
                                    ml_confidence = self.gradient_boosting_predictor.get_prediction_confidence(
                                        horse_data[horse_name], race
                                    )

                                    horse_pred['ml_prediction'] = {
                                        'finish_position': ml_prediction,
                                        'confidence': ml_confidence
                                    }

                            predictions['ml_enhanced'] = True
                            logger.info(f"Race {race_num}: ML predictions added")
                        except Exception as e:
                            logger.warning(f"ML prediction failed for race {race_num}: {e}")

                    # Add Kelly Criterion betting recommendations if available
                    if self.kelly_optimizer and predictions.get('predictions'):
                        try:
                            for horse_pred in predictions['predictions']:
                                win_prob = horse_pred.get('win_probability', 0) / 100.0
                                # Use morning line odds or default to 3.0
                                odds_str = horse_pred.get('morning_line_odds', '3-1')
                                decimal_odds = self._convert_odds_to_decimal(odds_str)

                                # Calculate Kelly recommendation (using default bankroll values)
                                kelly_result = self.kelly_optimizer.calculate_optimal_stake(
                                    win_probability=win_prob,
                                    decimal_odds=decimal_odds,
                                    current_bankroll=1000.0,  # Default bankroll
                                    initial_bankroll=1000.0
                                )

                                horse_pred['kelly_recommendation'] = kelly_result

                            predictions['kelly_enhanced'] = True
                            logger.info(f"Race {race_num}: Kelly Criterion recommendations added")
                        except Exception as e:
                            logger.warning(f"Kelly Criterion calculation failed for race {race_num}: {e}")

                    # Enhance with AI if available
                    if self.ai_analysis_enhancer and predictions.get('predictions'):
                        try:
                            # Get relevant horse data for this race
                            race_horse_data = []
                            for horse in race.get('horses', []):
                                horse_name = horse.get('name', '')
                                if horse_name in horse_data:
                                    race_horse_data.append(horse_data[horse_name])

                            # AI enhancement
                            ai_enhancement = await self.ai_analysis_enhancer.enhance_race_analysis(
                                race, predictions.get('predictions', []), {"horse_data": race_horse_data}
                            )

                            # Merge AI insights with predictions
                            predictions['ai_enhancement'] = ai_enhancement
                            predictions['enhanced'] = True

                            logger.info(f"Race {race_num}: AI enhancement completed")

                        except Exception as e:
                            logger.warning(f"AI enhancement failed for race {race_num}: {e}")
                            predictions['ai_enhancement'] = {"error": str(e)}
                            predictions['enhanced'] = False

                    race_analyses.append(predictions)
                    logger.info(f"Race {race_num}: analyzed {len(predictions.get('predictions', []))} horses")

                except Exception as e:
                    logger.error(f"Error analyzing race {race_num}: {e}")
                    # Add error placeholder
                    race_analyses.append({
                        'race_number': race_num,
                        'error': str(e),
                        'predictions': []
                    })

            return race_analyses

        except Exception as e:
            logger.error(f"Failed to analyze races: {e}")
            raise

    def _convert_odds_to_decimal(self, odds_str: str) -> float:
        """Convert morning line odds to decimal format"""
        try:
            if '-' in odds_str:
                # Handle fractional odds like "3-1", "5-2"
                parts = odds_str.split('-')
                if len(parts) == 2:
                    numerator = float(parts[0])
                    denominator = float(parts[1])
                    return (numerator / denominator) + 1.0
            elif '/' in odds_str:
                # Handle fractional odds like "3/1", "5/2"
                parts = odds_str.split('/')
                if len(parts) == 2:
                    numerator = float(parts[0])
                    denominator = float(parts[1])
                    return (numerator / denominator) + 1.0
            else:
                # Try to parse as decimal
                return float(odds_str)
        except (ValueError, TypeError):
            pass

        # Default to 3.0 (2-1 odds) if parsing fails
        return 3.0
    
    async def _generate_analysis_summary(self, race_analyses: List[Dict], session_id: str = None) -> Dict:
        """Generate enhanced summary statistics with AI betting recommendations"""
        try:
            total_races = len(race_analyses)
            successful_races = len([r for r in race_analyses if 'error' not in r])
            total_horses = sum(len(r.get('predictions', [])) for r in race_analyses)

            # Find best bets across all races
            all_predictions = []
            for race_analysis in race_analyses:
                if 'predictions' in race_analysis:
                    # Add race context to predictions
                    for pred in race_analysis['predictions']:
                        pred['race_number'] = race_analysis.get('race_number')
                    all_predictions.extend(race_analysis['predictions'])

            # Sort by composite rating and take top 3
            all_predictions.sort(key=lambda x: x.get('composite_rating', 0), reverse=True)
            best_bets = all_predictions[:3]

            # Generate AI betting recommendations if available
            betting_recommendations = {}
            if self.ai_client and race_analyses:
                try:
                    if session_id:
                        await self.session_manager.update_session_status(
                            session_id, "running", 95, "finalizing",
                            "Generating AI betting recommendations..."
                        )

                    betting_recommendations = await self.ai_client.generate_betting_recommendations(
                        race_analyses, bankroll=1000.0  # Default bankroll
                    )
                    logger.info("AI betting recommendations generated successfully")

                except Exception as e:
                    logger.warning(f"Failed to generate AI betting recommendations: {e}")
                    betting_recommendations = {"error": str(e)}

            # Calculate enhanced metrics
            ai_enhanced_races = len([r for r in race_analyses if r.get('enhanced', False)])
            confidence_scores = []

            for race_analysis in race_analyses:
                if race_analysis.get('ai_enhancement', {}).get('confidence_analysis'):
                    confidence_data = race_analysis['ai_enhancement']['confidence_analysis']
                    for horse, conf_data in confidence_data.items():
                        confidence_scores.append(conf_data.get('score', 0))

            avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0

            summary = {
                "total_races": total_races,
                "successful_races": successful_races,
                "total_horses": total_horses,
                "best_bets": best_bets,
                "success_rate": (successful_races / total_races * 100) if total_races > 0 else 0,
                "ai_enhanced_races": ai_enhanced_races,
                "ai_enhancement_rate": (ai_enhanced_races / total_races * 100) if total_races > 0 else 0,
                "average_confidence": avg_confidence,
                "betting_recommendations": betting_recommendations
            }

            return summary

        except Exception as e:
            logger.error(f"Failed to generate analysis summary: {e}")
            return {"error": str(e)}
