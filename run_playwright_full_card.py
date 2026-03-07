#!/usr/bin/env python3
"""
Complete Playwright-based pipeline for Del Mar race analysis.
Replaces the Selenium-based system with WAF-resistant Playwright scraping.
"""
import asyncio
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scrapers.playwright_integration import (
    build_smartpick_data_path,
    convert_overview_to_race_card,
    get_track_id,
    load_race_card,
    normalize_race_date,
    save_race_card_data,
    save_results,
    scrape_full_card_playwright,
)
from scrapers.smartpick_scraper import SmartPickRaceScraper
from race_entry_scraper import RaceEntryScraper
from race_prediction_engine import RacePredictionEngine

# Configure logging (config-aware)
try:
    from config.config_manager import ConfigManager
    _APP_CONFIG = ConfigManager().config
except Exception:
    _APP_CONFIG = None

_LOGS_DIR = str(getattr(_APP_CONFIG, 'logs_directory', 'logs'))
os.makedirs(_LOGS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(_LOGS_DIR, 'playwright_full_card.log')),
        logging.StreamHandler()
    ]
)

LOG = logging.getLogger('playwright_full_card')
def count_horses_with_profiles(card: Dict) -> int:
    """Count horses that have profile URLs"""
    count = 0
    for race in card.get('races', []):
        for horse in race.get('horses', []):
            if horse.get('profile_url'):
                count += 1
    return count


def generate_analysis_summary(race_analyses: List[Dict]) -> Dict:
    """Generate a UI-compatible summary for the current analysis run."""
    total_races = len(race_analyses)
    successful_races = len([race for race in race_analyses if 'error' not in race])
    total_horses = sum(len(race.get('predictions', [])) for race in race_analyses)

    all_predictions = []
    ai_enhanced_races = 0
    confidence_scores = []

    for race_analysis in race_analyses:
        if race_analysis.get('enhanced'):
            ai_enhanced_races += 1

        for prediction in race_analysis.get('predictions', []):
            best_bet = dict(prediction)
            best_bet.setdefault('race_number', race_analysis.get('race_number'))
            all_predictions.append(best_bet)

        confidence_analysis = race_analysis.get('ai_enhancement', {}).get('confidence_analysis', {})
        if isinstance(confidence_analysis, dict):
            for confidence_data in confidence_analysis.values():
                if isinstance(confidence_data, dict):
                    confidence_scores.append(confidence_data.get('score', 0))

    all_predictions.sort(key=lambda prediction: prediction.get('composite_rating', 0), reverse=True)

    average_confidence = (
        sum(confidence_scores) / len(confidence_scores)
        if confidence_scores else 0
    )

    return {
        'total_races': total_races,
        'successful_races': successful_races,
        'total_horses': total_horses,
        'best_bets': all_predictions[:3],
        'success_rate': (successful_races / total_races * 100) if total_races else 0,
        'ai_enhanced_races': ai_enhanced_races,
        'ai_enhancement_rate': (ai_enhanced_races / total_races * 100) if total_races else 0,
        'average_confidence': average_confidence,
        'betting_recommendations': {},
    }


async def get_race_count_from_card_page(track_id: str, date_str: str) -> int:
    """
    Scrape the race card overview page to get the actual number of races

    Args:
        track_id: Track code (e.g., 'SA', 'DMR')
        date_str: Date in MM/DD/YYYY format

    Returns:
        Number of races on the card
    """
    from playwright.async_api import async_playwright

    # Convert date to MMDDYY format for URL
    # date_str is in MM/DD/YYYY format
    month, day, year = date_str.split('/')
    date_code = f"{month}{day}{year[2:]}"  # MMDDYY

    # Build URL: https://www.equibase.com/static/entry/SA100525USA-EQB.html
    url = f"https://www.equibase.com/static/entry/{track_id}{date_code}USA-EQB.html"
    LOG.info(f"🔍 Fetching race count from: {url}")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )

            # Reduce memory / speed up: block heavy resources
            async def _route_handler(route, request):
                try:
                    if request.resource_type in {"image", "media", "font"}:
                        await route.abort()
                    else:
                        await route.continue_()
                except Exception:
                    try:
                        await route.continue_()
                    except Exception:
                        pass
            await context.route("**/*", _route_handler)

            page = await context.new_page()

            # Navigate to race card page
            response = await page.goto(url, wait_until='load', timeout=45000)

            if response is None or response.status != 200:
                LOG.warning(f"⚠️  Race card page returned status {getattr(response, 'status', 'None')}")
                await browser.close()
                return 8  # Default fallback

            # Wait a bit for content to settle
            await page.wait_for_timeout(1000)

            # Count race sections - robust multi-strategy
            race_count = await page.evaluate('''
                () => {
                    const raceNumbers = new Set();

                    // Strategy A: Anchors or IDs like #race1, #Race1, etc.
                    const byAnchor = Array.from(document.querySelectorAll('a[href^="#"], [id], [name]'));
                    byAnchor.forEach(el => {
                        const attrs = [el.getAttribute('href') || '', el.id || '', el.getAttribute('name') || ''].join(' ');
                        const m = attrs.match(/(?:^|#|\b)race[-_\s]*([0-9]{1,2})\b/i);
                        if (m) raceNumbers.add(parseInt(m[1]));
                    });

                    // Strategy B: Visible headings containing "Race N"
                    const headerEls = document.querySelectorAll('h1,h2,h3,h4,.race,.entry,.race-header,.raceTitle, .race-title, .raceHeader');
                    headerEls.forEach(el => {
                        const t = (el.textContent || '').replace(/\s+/g,' ').trim();
                        const m = t.match(/Race\s*#?\s*([0-9]{1,2})\b/i);
                        if (m) raceNumbers.add(parseInt(m[1]));
                    });

                    // Strategy C: Links/hrefs carrying raceNumber param
                    const links = document.querySelectorAll('a[href]');
                    links.forEach(a => {
                        const href = a.getAttribute('href') || '';
                        const m = href.match(/raceNumber=(\d{1,2})/i);
                        if (m) raceNumbers.add(parseInt(m[1]));
                    });

                    // Strategy D: Global text fallback
                    const bodyText = (document.body.innerText || '').replace(/\s+/g,' ');
                    let m;
                    const re = /\bRace\s*#?\s*([0-9]{1,2})\b/gi;
                    while ((m = re.exec(bodyText)) !== null) {
                        raceNumbers.add(parseInt(m[1]));
                    }

                    if (raceNumbers.size === 0) return 0;
                    return Math.max(...Array.from(raceNumbers));
                }
            ''')

            await browser.close()

            if race_count and race_count > 0:
                LOG.info(f"✅ Found {race_count} races on card")
                return race_count
            else:
                LOG.warning(f"⚠️  Could not determine race count from Playwright (got {race_count}), trying fallback")
                # Don't return yet, let the fallback try

    except Exception as e:
        LOG.error(f"❌ Error fetching race count via Playwright: {e}")
        import traceback
        LOG.error(f"Traceback: {traceback.format_exc()}")

    # Final fallback: try simple HTTP fetch + regex parsing (works for static entry pages)
    LOG.info(f"🔄 Trying HTTP fallback for race count from {url}")
    try:
        import re, requests
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
        }
        resp = requests.get(url, headers=headers, timeout=15)
        LOG.info(f"HTTP fallback status: {resp.status_code}")
        if resp.status_code == 200 and resp.text:
            numbers = set(int(n) for n in re.findall(r"\bRace\s*#?\s*([0-9]{1,2})\b", resp.text, flags=re.I))
            LOG.info(f"Found race numbers in HTML: {sorted(numbers) if numbers else 'none'}")
            if numbers:
                race_count = max(numbers)
                LOG.info(f"✅ (HTTP fallback) Found {race_count} races on card")
                return race_count
        LOG.warning("⚠️  (HTTP fallback) Could not determine race count from static HTML")
    except Exception as e2:
        LOG.error(f"❌ (HTTP fallback) Error parsing static entry page: {e2}")
        import traceback
        LOG.error(f"Traceback: {traceback.format_exc()}")

    LOG.warning("⚠️  All race count detection methods failed, using default of 8")
    return 8  # Default fallback


async def scrape_smartpick_data_for_card(date_str: str, num_races: int) -> Dict:
    """Scrape SmartPick data for all races on the card using Playwright"""
    LOG.info(f"🎯 Scraping SmartPick data for {num_races} races on {date_str}")

    # Get track ID from environment variable
    track_id = get_track_id()
    LOG.info(f"Using track ID: {track_id}")

    # Use Playwright-based scraper to bypass WAF
    from scrapers.smartpick_playwright import scrape_multiple_races_playwright

    try:
        # Scrape all races with a single browser instance
        all_races_data = await scrape_multiple_races_playwright(track_id, date_str, num_races, "D")

        # Convert to the expected format
        all_smartpick_data = {}
        for race_num, horses in all_races_data.items():
            all_smartpick_data[race_num] = horses
            LOG.info(f"  ✅ Race {race_num}: {len(horses)} horses")

        smartpick_path = build_smartpick_data_path(track_id, date_str)
        with open(smartpick_path, 'w') as f:
            json.dump(all_smartpick_data, f, indent=2)
        LOG.info(f"💾 SmartPick data saved to {smartpick_path}")

        return all_smartpick_data

    except Exception as e:
        LOG.error(f"❌ Error scraping SmartPick data: {e}")
        return {}


def scrape_smartpick_data_for_card_OLD_REQUESTS_VERSION(date_str: str, num_races: int) -> Dict:
    """OLD VERSION - Scrape SmartPick data for all races on the card (BLOCKED BY WAF)"""
    LOG.info(f"🎯 Scraping SmartPick data for {num_races} races on {date_str}")

    # Get track ID from environment variable
    track_id = os.environ.get('TRACK_ID', 'DMR')
    LOG.info(f"Using track ID: {track_id}")

    smartpick_scraper = SmartPickRaceScraper()
    all_smartpick_data = {}

    # SmartPick URLs expect MM/DD/YYYY format (gets URL encoded automatically)
    # The date_str should already be in MM/DD/YYYY format
    smartpick_date = date_str

    for race_num in range(1, num_races + 1):
        try:
            LOG.info(f"  📊 Scraping SmartPick Race {race_num}...")

            # Build URL for debugging
            from scrapers.smartpick_scraper import smartpick_url
            url = smartpick_url(track_id, smartpick_date, race_num, "D")
            LOG.info(f"    🌐 URL: {url}")

            race_data = smartpick_scraper.scrape_race(track_id, smartpick_date, race_num, "D")

            if race_data:
                all_smartpick_data[race_num] = race_data
                horse_count = len(race_data)
                LOG.info(f"    ✅ Found {horse_count} horses with SmartPick data")

                # Log first horse as example
                if race_data:
                    first_horse = list(race_data.keys())[0]
                    LOG.info(f"    📊 Example: {first_horse}")
            else:
                LOG.warning(f"    ⚠️  No SmartPick data found for race {race_num}")
                LOG.warning(f"    💡 This may be normal if race {race_num} has already finished or is not available")

        except Exception as e:
            LOG.error(f"    ❌ Error scraping SmartPick race {race_num}: {e}")
            import traceback
            LOG.error(f"    📋 Traceback: {traceback.format_exc()}")

        # Small delay between requests to be respectful
        time.sleep(2)  # Increased delay to be more respectful

    # Report results
    successful_races = len(all_smartpick_data)
    total_horses = sum(len(race_data) for race_data in all_smartpick_data.values())

    LOG.info(f"📊 SmartPick Results Summary:")
    LOG.info(f"  ✅ Successful races: {successful_races}/{num_races}")
    LOG.info(f"  🐎 Total horses found: {total_horses}")

    if successful_races > 0:
        LOG.info(f"  🎯 Races with data: {list(all_smartpick_data.keys())}")
    else:
        LOG.warning(f"  ⚠️  No SmartPick data found for any race on {date_str}")
        LOG.warning(f"  💡 This may be normal if all races have finished or SmartPick is not available for this date")

    # Save SmartPick data
    smartpick_filename = f"smartpick_data_{date_str.replace('/', '_')}.json"
    with open(smartpick_filename, 'w') as f:
        json.dump(all_smartpick_data, f, indent=2)
    LOG.info(f"💾 SmartPick data saved to {smartpick_filename}")

    return all_smartpick_data


def merge_smartpick_with_horse_data(horse_data: Dict, smartpick_data: Dict) -> Dict:
    """Merge SmartPick data with horse profile data"""
    LOG.info("🔗 Merging SmartPick data with horse profiles")

    merged_count = 0
    enhanced_count = 0

    for race_num_str, race_smartpick in smartpick_data.items():
        for horse_name, sp_data in race_smartpick.items():
            # Try to find matching horse in horse_data
            matched_horse = None

            # Try exact match first
            if horse_name in horse_data:
                matched_horse = horse_name
            else:
                # Try fuzzy matching (remove state abbreviations, etc.)
                clean_sp_name = re.sub(r'\s*\([A-Z]{2,3}\)\s*$', '', horse_name).strip()

                for hd_name in horse_data.keys():
                    clean_hd_name = re.sub(r'\s*\([A-Z]{2,3}\)\s*$', '', hd_name).strip()
                    if clean_sp_name.lower() == clean_hd_name.lower():
                        matched_horse = hd_name
                        break

            if matched_horse:
                # Merge SmartPick data into horse data
                if 'smartpick' not in horse_data[matched_horse]:
                    horse_data[matched_horse]['smartpick'] = {}

                # Copy SmartPick data
                horse_data[matched_horse]['smartpick'].update(sp_data.get('smartpick', {}))

                # Copy enhanced data if available
                if 'our_speed_figure' in sp_data:
                    horse_data[matched_horse]['our_speed_figure'] = sp_data['our_speed_figure']
                    enhanced_count += 1

                if 'last3_results' in sp_data and sp_data['last3_results']:
                    horse_data[matched_horse]['last3_results'] = sp_data['last3_results']

                if 'workouts_last3' in sp_data and sp_data['workouts_last3']:
                    horse_data[matched_horse]['workouts_last3'] = sp_data['workouts_last3']

                merged_count += 1

    LOG.info(f"✅ Merged SmartPick data for {merged_count} horses")
    LOG.info(f"✅ Enhanced speed figures for {enhanced_count} horses")

    return horse_data


async def scrape_horses():
    """Scrape horse data using Playwright"""
    LOG.info("=== Playwright-Based Full Card Analysis ===")
    date_str = normalize_race_date()
    track_id = get_track_id()
    os.environ['RACE_DATE_STR'] = date_str
    os.environ['TRACK_ID'] = track_id

    LOG.info(f"Date: {date_str}")

    # Load or scrape race card to check profile URLs
    card = load_race_card()
    total_horses = sum(len(race.get('horses', [])) for race in card.get('races', []))
    horses_with_profiles = count_horses_with_profiles(card)

    LOG.info(f"Total horses in card: {total_horses}")
    LOG.info(f"Horses with profile URLs: {horses_with_profiles}")

    # Scrape SmartPick data for all races
    LOG.info("=== SmartPick Data Collection ===")

    # First, try to get race count from the saved card
    unique_race_numbers = set()
    for race in card.get('races', []):
        race_num = race.get('race_number')
        if race_num:
            unique_race_numbers.add(race_num)

    # If no races in saved card, fetch from race card page
    if not unique_race_numbers:
        LOG.info(f"No races in saved card, fetching race count from Equibase for {track_id} on {date_str}")
        num_races = await get_race_count_from_card_page(track_id, date_str)
    else:
        num_races = len(unique_race_numbers)

    LOG.info(f"Scraping SmartPick data for {num_races} races")
    smartpick_data = await scrape_smartpick_data_for_card(date_str, num_races)

    if horses_with_profiles == 0:
        LOG.info("No horses with profile URLs found in saved card; scraping card now.")
        # Proactively scrape card for the given date and retry
        from race_entry_scraper import RaceEntryScraper
        scraper = RaceEntryScraper()
        url = scraper.build_card_overview_url(track_id, date_str, 'USA')
        LOG.info(f"Scraping race card from: {url}")
        try:
            # Use direct await since we're already in an async context
            overview_result = await scraper.scrape_card_overview(track_id, date_str, 'USA')
            if overview_result and overview_result.get('races'):
                # Convert overview to race card format and save
                race_card_data = convert_overview_to_race_card(overview_result, date_str, track_id)
                save_race_card_data(race_card_data, date_str, track_id)
                card = load_race_card()
                total_horses = sum(len(race.get('horses', [])) for race in card.get('races', []))
                horses_with_profiles = count_horses_with_profiles(card)
                LOG.info(f"Total horses in card: {total_horses}")
                LOG.info(f"Horses with profile URLs: {horses_with_profiles}")
        except Exception as e:
            LOG.error(f"Failed to scrape race card: {e}")
            return {}

    LOG.info("Starting Playwright-based horse scraping...")

    try:
        # Add timeout to prevent hanging (30 minutes max)
        import asyncio
        results = await asyncio.wait_for(scrape_full_card_playwright(), timeout=1800)

        if results:
            save_results(results)
            LOG.info(f"Successfully scraped {len(results)} horses")

            # Print summary
            for horse_name, data in results.items():
                results_count = len(data.get('last3_results', []))
                workouts_count = len(data.get('workouts_last3', []))
                quality = data.get('quality_rating', 0)
                LOG.info(f"  {horse_name}: {results_count} results, {workouts_count} workouts, quality={quality}")
        else:
            LOG.warning("No horses were successfully scraped")

        return results

    except asyncio.TimeoutError:
        LOG.error("Scraping timed out after 30 minutes")
        return {}
    except Exception as e:
        LOG.error(f"Error during Playwright scraping: {e}")
        import traceback
        LOG.error(f"Traceback: {traceback.format_exc()}")
        return {}


def run_analysis(horse_data: Optional[Dict] = None) -> Dict:
    """Run the race analysis with scraped data"""
    LOG.info("=== Running Race Analysis ===")
    analysis_started_at = time.time()

    try:
        if horse_data is None:
            horse_data_path = "real_equibase_horse_data.json"
            if not os.path.exists(horse_data_path):
                message = f"Horse data file not found: {horse_data_path}"
                LOG.error(message)
                return {'error': message}

            with open(horse_data_path, 'r') as f:
                horse_data = json.load(f)

        LOG.info(f"Loaded data for {len(horse_data)} horses")

        # Load SmartPick data
        date_str = normalize_race_date()
        track_id = get_track_id()
        smartpick_path = build_smartpick_data_path(track_id, date_str)
        smartpick_data = {}

        if os.path.exists(smartpick_path):
            with open(smartpick_path, 'r') as f:
                smartpick_data = json.load(f)
            LOG.info(f"Loaded SmartPick data for {len(smartpick_data)} races")
        else:
            LOG.warning(f"SmartPick data file not found: {smartpick_path}")

        # Merge SmartPick data with horse data
        horse_data = merge_smartpick_with_horse_data(horse_data, smartpick_data)
        
        # Load race card
        card = load_race_card()
        if not card:
            message = "Race card not found"
            LOG.error(message)
            return {'error': message}
            
        # Initialize prediction engine
        engine = RacePredictionEngine()

        # Analyze each race
        all_race_analyses = []

        for race in card.get('races', []):
            race_num = race.get('race_number', 0)
            LOG.info(f"Analyzing Race {race_num}")

            # Analyze race using prediction engine with full race dict and horse_data mapping
            try:
                predictions = engine.predict_race(race, horse_data)
                all_race_analyses.append(predictions)
                LOG.info(f"Race {race_num}: analyzed {len(predictions.get('predictions', []))} horses")
            except Exception as e:
                LOG.error(f"Error analyzing race {race_num}: {e}")
                all_race_analyses.append({
                    'race_number': race_num,
                    'race_type': race.get('race_type', ''),
                    'distance': race.get('distance', ''),
                    'surface': race.get('surface', ''),
                    'error': str(e),
                    'predictions': [],
                })

        summary = generate_analysis_summary(all_race_analyses)
        final_results = {
            'race_date': date_str,
            'track_id': track_id,
            'analysis_duration_seconds': time.time() - analysis_started_at,
            'total_races': len(card.get('races', [])),
            'total_horses': len(horse_data),
            'race_card': card,
            'horse_data': horse_data,
            'race_analyses': all_race_analyses,
            'generated_at': datetime.now().isoformat(),
            'summary': summary,
            'ai_services_used': {
                'openrouter_client': False,
                'scraping_assistant': False,
                'analysis_enhancer': False,
            },
        }

        # Save analysis results
        output_path = f"analysis_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_path, 'w') as f:
            json.dump(final_results, f, indent=2)
            
        LOG.info(f"Analysis complete. Results saved to {output_path}")
        LOG.info(f"Analyzed {len(all_race_analyses)} races")
        
        return final_results
        
    except Exception as e:
        LOG.error(f"Error during analysis: {e}")
        return {'error': str(e)}


async def main():
    """Main entry point"""
    pipeline_started_at = time.time()
    try:
        # Step 1: Scrape horse data using Playwright
        horse_results = await scrape_horses()
        
        if not horse_results:
            message = "No horse data scraped. Cannot proceed with analysis."
            LOG.error(message)
            return {
                'error': message,
                'race_date': normalize_race_date(),
                'track_id': get_track_id(),
                'generated_at': datetime.now().isoformat(),
            }
        
        # Step 2: Run race analysis
        analysis_results = run_analysis(horse_results)
        if analysis_results:
            analysis_results['analysis_duration_seconds'] = time.time() - pipeline_started_at
        
        if analysis_results and not analysis_results.get('error'):
            LOG.info("=== Pipeline Complete ===")
            LOG.info(f"Successfully analyzed {len(analysis_results.get('race_analyses', []))} races")
            LOG.info(f"Horse data: {len(horse_results)} horses")
            return analysis_results
        else:
            LOG.warning("Analysis completed but no results generated")
            return analysis_results or {
                'error': 'Analysis completed without returning results',
                'race_date': normalize_race_date(),
                'track_id': get_track_id(),
                'generated_at': datetime.now().isoformat(),
            }
            
    except Exception as e:
        LOG.error(f"Pipeline failed: {e}")
        return {
            'error': str(e),
            'race_date': normalize_race_date(),
            'track_id': get_track_id(),
            'generated_at': datetime.now().isoformat(),
        }


if __name__ == "__main__":
    # Ensure logs directory exists (respect config if available)
    try:
        _dir = _LOGS_DIR
    except NameError:
        _dir = 'logs'
    os.makedirs(_dir, exist_ok=True)

    # Run the async pipeline
    asyncio.run(main())
