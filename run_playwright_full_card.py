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
from typing import Dict, List

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scrapers.playwright_integration import scrape_full_card_playwright, save_results, load_race_card
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


def convert_overview_to_race_card(overview_result: Dict, date_str: str) -> Dict:
    """Convert race overview data to race card format"""
    races = []

    for race_overview in overview_result.get('races', []):
        race_number = race_overview.get('race_number', 1)

        # Filter horses to only include actual race entries (not sires/dams)
        race_horses = []
        seen_names = set()

        for horse_data in race_overview.get('horses', []):
            horse_name = horse_data.get('name', '')
            profile_url = horse_data.get('profile_url', '')

            # Skip if we've seen this horse or if it's clearly a sire/dam
            if horse_name in seen_names:
                continue
            if not profile_url or 'refno=' not in profile_url:
                continue

            # Basic filtering for actual race entries vs sires/dams
            # Race entries typically have state abbreviations in parentheses
            if '(' in horse_name and ')' in horse_name:
                race_horses.append({
                    'name': horse_name,
                    'post_position': len(race_horses) + 1,
                    'jockey': 'TBD',
                    'trainer': 'TBD',
                    'weight': 120,
                    'morning_line_odds': '5/1',
                    'age': 3,
                    'sex': 'C',
                    'equipment_changes': '',
                    'claiming_price': None,
                    'profile_url': profile_url
                })
                seen_names.add(horse_name)

                # Reasonable limit for race entries
                if len(race_horses) >= 20:
                    break

        race_data = {
            'race_number': race_number,
            'post_time': f'{2 + race_number}:30 PM PT',
            'race_type': 'TBD',
            'purse': '$50,000',
            'distance': '6 Furlongs',
            'surface': 'Dirt',
            'conditions': 'TBD',
            'horses': race_horses
        }
        races.append(race_data)

    return {
        'date': date_str,
        'races': races
    }


def save_race_card_data(race_card_data: Dict, date_str: str):
    """Save race card data to JSON file"""
    import json
    filename = f"del_mar_{date_str.replace('/', '_')}_races.json"
    with open(filename, 'w') as f:
        json.dump(race_card_data, f, indent=2)
    print(f"Race card saved to {filename}")


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
            page = await context.new_page()

            # Navigate to race card page
            response = await page.goto(url, wait_until='domcontentloaded', timeout=30000)

            if response.status != 200:
                LOG.warning(f"⚠️  Race card page returned status {response.status}")
                await browser.close()
                return 8  # Default fallback

            # Wait a bit for content to load
            await page.wait_for_timeout(2000)

            # Count race sections - look for race headers
            race_count = await page.evaluate('''
                () => {
                    // Method 1: Look for race number headers
                    const raceHeaders = document.querySelectorAll('[class*="race"], [id*="race"], h2, h3');
                    const raceNumbers = new Set();

                    raceHeaders.forEach(el => {
                        const text = el.textContent || '';
                        // Look for "Race 1", "Race 2", etc.
                        const match = text.match(/Race\\s+(\\d+)/i);
                        if (match) {
                            raceNumbers.add(parseInt(match[1]));
                        }
                    });

                    if (raceNumbers.size > 0) {
                        return Math.max(...raceNumbers);
                    }

                    // Method 2: Count tables (each race usually has a table)
                    const tables = document.querySelectorAll('table');
                    if (tables.length > 0) {
                        return tables.length;
                    }

                    // Method 3: Look for race links
                    const links = document.querySelectorAll('a[href*="raceNumber"]');
                    const linkRaceNumbers = new Set();
                    links.forEach(link => {
                        const href = link.getAttribute('href') || '';
                        const match = href.match(/raceNumber=(\\d+)/);
                        if (match) {
                            linkRaceNumbers.add(parseInt(match[1]));
                        }
                    });

                    if (linkRaceNumbers.size > 0) {
                        return Math.max(...linkRaceNumbers);
                    }

                    return 0;
                }
            ''')

            await browser.close()

            if race_count > 0:
                LOG.info(f"✅ Found {race_count} races on card")
                return race_count
            else:
                LOG.warning(f"⚠️  Could not determine race count, using default of 8")
                return 8

    except Exception as e:
        LOG.error(f"❌ Error fetching race count: {e}")
        return 8  # Default fallback


async def scrape_smartpick_data_for_card(date_str: str, num_races: int) -> Dict:
    """Scrape SmartPick data for all races on the card using Playwright"""
    LOG.info(f"🎯 Scraping SmartPick data for {num_races} races on {date_str}")

    # Get track ID from environment variable
    track_id = os.environ.get('TRACK_ID', 'DMR')
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
    date_str = os.environ.get('RACE_DATE_STR', '09/07/2025')  # Updated to 09/07/2025

    # Convert date format if needed (YYYY-MM-DD to MM/DD/YYYY)
    if len(date_str) == 10 and date_str[4] == '-' and date_str[7] == '-':
        # Convert from YYYY-MM-DD to MM/DD/YYYY
        year, month, day = date_str.split('-')
        date_str = f"{month}/{day}/{year}"
        os.environ['RACE_DATE_STR'] = date_str  # Update environment variable
        LOG.info(f"Converted date format to: {date_str}")

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
        track_id = os.environ.get('TRACK_ID', 'DMR')
        LOG.info(f"No races in saved card, fetching race count from Equibase for {track_id} on {date_str}")
        num_races = await get_race_count_from_card_page(track_id, date_str)
    else:
        num_races = len(unique_race_numbers)

    LOG.info(f"Scraping SmartPick data for {num_races} races")
    smartpick_data = await scrape_smartpick_data_for_card(date_str, num_races)

    if horses_with_profiles == 0:
        LOG.info("No horses with profile URLs found in saved card; scraping card now.")
        # Proactively scrape card for the given date and retry
        # Use the already converted date_str from above
        # Get track ID from environment variable
        track_id = os.environ.get('TRACK_ID', 'DMR')
        from race_entry_scraper import RaceEntryScraper
        scraper = RaceEntryScraper()
        url = scraper.build_card_overview_url(track_id, date_str, 'USA')
        LOG.info(f"Scraping race card from: {url}")
        try:
            # Use direct await since we're already in an async context
            overview_result = await scraper.scrape_card_overview(track_id, date_str, 'USA')
            if overview_result and overview_result.get('races'):
                # Convert overview to race card format and save
                race_card_data = convert_overview_to_race_card(overview_result, date_str)
                save_race_card_data(race_card_data, date_str)
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


def run_analysis():
    """Run the race analysis with scraped data"""
    LOG.info("=== Running Race Analysis ===")

    try:
        # Load horse data
        horse_data_path = "real_equibase_horse_data.json"
        if not os.path.exists(horse_data_path):
            LOG.error(f"Horse data file not found: {horse_data_path}")
            return

        with open(horse_data_path, 'r') as f:
            horse_data = json.load(f)

        LOG.info(f"Loaded data for {len(horse_data)} horses")

        # Load SmartPick data
        date_str = os.environ.get('RACE_DATE_STR', '09/05/2025')
        smartpick_path = f"smartpick_data_{date_str.replace('/', '_')}.json"
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
            LOG.error("Race card not found")
            return
            
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

        # Save analysis results
        output_path = f"analysis_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_path, 'w') as f:
            json.dump(all_race_analyses, f, indent=2)
            
        LOG.info(f"Analysis complete. Results saved to {output_path}")
        LOG.info(f"Analyzed {len(all_race_analyses)} races")
        
        return all_race_analyses
        
    except Exception as e:
        LOG.error(f"Error during analysis: {e}")
        raise


async def main():
    """Main entry point"""
    try:
        # Step 1: Scrape horse data using Playwright
        horse_results = await scrape_horses()
        
        if not horse_results:
            LOG.error("No horse data scraped. Cannot proceed with analysis.")
            return
        
        # Step 2: Run race analysis
        analysis_results = run_analysis()
        
        if analysis_results:
            LOG.info("=== Pipeline Complete ===")
            LOG.info(f"Successfully analyzed {len(analysis_results)} races")
            LOG.info(f"Horse data: {len(horse_results)} horses")
        else:
            LOG.warning("Analysis completed but no results generated")
            
    except Exception as e:
        LOG.error(f"Pipeline failed: {e}")
        raise


if __name__ == "__main__":
    # Ensure logs directory exists (respect config if available)
    try:
        _dir = _LOGS_DIR
    except NameError:
        _dir = 'logs'
    os.makedirs(_dir, exist_ok=True)

    # Run the async pipeline
    asyncio.run(main())
