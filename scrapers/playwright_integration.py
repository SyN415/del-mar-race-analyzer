#!/usr/bin/env python3
"""
Integration layer to use Playwright scraper with existing pipeline.
Replaces Selenium-based scraping with Playwright for WAF bypass.
"""
import asyncio
import json
import os
from typing import Dict, List, Tuple

from scrapers.playwright_equibase_scraper import PlaywrightEquibaseScraper
from race_entry_scraper import RaceEntryScraper
# # from scrapers.equibase_scraper import DelMarEquibaseCollector
from utils.equipment_normalizer import normalize_horse
import logging

logger = logging.getLogger(__name__)


async def scrape_overview():
    """Scrape race card overview using RaceEntryScraper"""
    try:
        date_str = os.environ.get('RACE_DATE_STR', '09/07/2025')  # Updated to 09/07/2025

        # Convert date format if needed (YYYY-MM-DD to MM/DD/YYYY)
        if len(date_str) == 10 and date_str[4] == '-' and date_str[7] == '-':
            # Convert from YYYY-MM-DD to MM/DD/YYYY
            year, month, day = date_str.split('-')
            date_str = f"{month}/{day}/{year}"
            print(f"Converted date format to: {date_str}")

        scraper = RaceEntryScraper()
        result = await scraper.scrape_card_overview('DMR', date_str, 'USA')
        return result
    except Exception as e:
        print(f"Failed to scrape overview: {e}")
        import traceback
        traceback.print_exc()
        return None


def convert_overview_to_race_card(overview_result: Dict, date_str: str) -> Dict:
    """Convert overview result to race card format"""
    try:
        if not overview_result or not overview_result.get('races'):
            return {}

        races_data = []
        for r in overview_result['races']:
            race_data = {
                'race_number': getattr(r, 'race_number', 0),
                'post_time': getattr(r, 'post_time', ''),
                'race_type': getattr(r, 'race_type', ''),
                'purse': getattr(r, 'purse', ''),
                'distance': getattr(r, 'distance', ''),
                'surface': getattr(r, 'surface', ''),
                'conditions': getattr(r, 'conditions', ''),
                'horses': []
            }

            # Convert horses
            for horse in getattr(r, 'horses', []):
                horse_data = {
                    'name': getattr(horse, 'name', ''),
                    'post_position': getattr(horse, 'post_position', 0),
                    'jockey': getattr(horse, 'jockey', ''),
                    'trainer': getattr(horse, 'trainer', ''),
                    'weight': getattr(horse, 'weight', 0),
                    'morning_line_odds': getattr(horse, 'morning_line_odds', ''),
                    'profile_url': getattr(horse, 'profile_url', '')
                }
                race_data['horses'].append(horse_data)

            races_data.append(race_data)

        return {
            'date': date_str,
            'track': 'Del Mar',
            'track_code': 'DMR',
            'races': races_data
        }
    except Exception as e:
        print(f"Failed to convert overview to race card: {e}")
        return {}


def save_race_card_data(race_card_data: Dict, date_str: str):
    """Save race card data to JSON file"""
    try:
        filename = f"del_mar_{date_str.replace('/', '_')}_races.json"
        with open(filename, 'w') as f:
            json.dump(race_card_data, f, indent=2)
        print(f"Saved race card data to {filename}")
    except Exception as e:
        print(f"Failed to save race card data: {e}")


def validate_scraping_consistency(horse_data: Dict) -> Dict:
    """
    Verify consistency between SmartPick and Equibase data sources
    Implements cross-source verification with discrepancy tracking
    """
    validation_flags = horse_data.get('validation_flags', [])

    # Get data from both sources
    smartpick_data = horse_data.get('smartpick', {})
    equibase_data = horse_data.get('equibase', horse_data)  # Fallback to main data

    # Verify speed figures match within 5%
    sp_speed = smartpick_data.get('our_speed_figure') or smartpick_data.get('speed_figure')
    eq_speed = equibase_data.get('speed_score') or equibase_data.get('our_speed_figure')

    if sp_speed and eq_speed:
        try:
            sp_speed = float(sp_speed)
            eq_speed = float(eq_speed)
            diff = abs(sp_speed - eq_speed)
            diff_pct = (diff / max(sp_speed, eq_speed)) * 100

            if diff_pct > 10:  # More than 10% difference
                validation_flags.append({
                    'type': 'SPEED_DISCREPANCY',
                    'value': diff_pct,
                    'severity': 'HIGH' if diff_pct > 20 else 'MEDIUM',
                    'smartpick_value': sp_speed,
                    'equibase_value': eq_speed
                })
                logger.warning(f"Speed discrepancy detected: {diff_pct:.1f}% difference")
        except (ValueError, TypeError):
            validation_flags.append({
                'type': 'SPEED_PARSE_ERROR',
                'severity': 'LOW',
                'smartpick_value': sp_speed,
                'equibase_value': eq_speed
            })

    # Verify jockey/trainer consistency
    sp_jockey = smartpick_data.get('jockey', '')
    eq_jockey = equibase_data.get('jockey', '')

    if sp_jockey and eq_jockey and sp_jockey.lower() != eq_jockey.lower():
        validation_flags.append({
            'type': 'JOCKEY_MISMATCH',
            'severity': 'MEDIUM',
            'smartpick_value': sp_jockey,
            'equibase_value': eq_jockey
        })

    sp_trainer = smartpick_data.get('trainer', '')
    eq_trainer = equibase_data.get('trainer', '')

    if sp_trainer and eq_trainer and sp_trainer.lower() != eq_trainer.lower():
        validation_flags.append({
            'type': 'TRAINER_MISMATCH',
            'severity': 'MEDIUM',
            'smartpick_value': sp_trainer,
            'equibase_value': eq_trainer
        })

    # Calculate data consistency score
    total_checks = 0
    passed_checks = 0

    # Speed consistency check
    if sp_speed and eq_speed:
        total_checks += 1
        try:
            diff_pct = abs(float(sp_speed) - float(eq_speed)) / max(float(sp_speed), float(eq_speed)) * 100
            if diff_pct <= 10:
                passed_checks += 1
        except (ValueError, TypeError):
            pass

    # Jockey consistency check
    if sp_jockey and eq_jockey:
        total_checks += 1
        if sp_jockey.lower() == eq_jockey.lower():
            passed_checks += 1

    # Trainer consistency check
    if sp_trainer and eq_trainer:
        total_checks += 1
        if sp_trainer.lower() == eq_trainer.lower():
            passed_checks += 1

    consistency_score = (passed_checks / total_checks * 100) if total_checks > 0 else 100

    # Update horse data with validation results
    horse_data['validation_flags'] = validation_flags
    horse_data['consistency_score'] = consistency_score
    horse_data['data_sources'] = {
        'smartpick_available': bool(smartpick_data),
        'equibase_available': bool(equibase_data),
        'cross_validated': total_checks > 0
    }

    if consistency_score < 85:
        logger.warning(f"Low consistency score: {consistency_score:.1f}% for horse data")

    return horse_data


def count_horses_with_profiles(card: Dict) -> int:
    """Count horses that have profile URLs"""
    count = 0
    for race in card.get('races', []):
        for horse in race.get('horses', []):
            if horse.get('profile_url'):
                count += 1
    return count


def load_race_card() -> Dict:
    """Load or scrape the race card for the date specified by RACE_DATE_STR."""
    date_str = os.environ.get('RACE_DATE_STR', '09/07/2025')  # Updated to 09/07/2025

    # Convert date format if needed (YYYY-MM-DD to MM/DD/YYYY)
    if len(date_str) == 10 and date_str[4] == '-' and date_str[7] == '-':
        # Convert from YYYY-MM-DD to MM/DD/YYYY
        year, month, day = date_str.split('-')
        date_str = f"{month}/{day}/{year}"
        print(f"Converted date format to: {date_str}")

    card_path = os.environ.get("RACE_CARD_PATH", f"del_mar_{date_str.replace('/', '_')}_races.json")

    # Force fresh scrape by checking if file has placeholder URLs
    if os.path.exists(card_path):
        try:
            with open(card_path, 'r') as f:
                existing_data = json.load(f)
            # Check if data has placeholder URLs - if so, re-scrape
            has_placeholders = False
            for race in existing_data.get('races', []):
                for horse in race.get('horses', []):
                    if 'PLACEHOLDER' in horse.get('profile_url', ''):
                        has_placeholders = True
                        break
                if has_placeholders:
                    break

            if not has_placeholders:
                print(f"Loading existing race card from {card_path}")
                return existing_data
            else:
                print(f"Found placeholder URLs in {card_path}, forcing fresh scrape...")
        except Exception as e:
            print(f"Error reading existing race card: {e}")

    # Not found or has placeholders → scrape via RaceEntryScraper
    try:
        import asyncio
        scraper = RaceEntryScraper()
        
        async def scrape_card():
            result = await scraper.scrape_card_overview('DMR', date_str, 'USA')
            return result
        
        # Use existing event loop if available
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create a task instead of using asyncio.run
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, scrape_card())
                    overview_result = future.result()
            else:
                overview_result = asyncio.run(scrape_card())
        except:
            overview_result = None
        if overview_result and overview_result.get('races'):
            races_data = [{
                'race_number': getattr(r, 'race_number', 0),
                'post_time': getattr(r, 'post_time', ''),
                'race_type': getattr(r, 'race_type', ''),
                'purse': getattr(r, 'purse', ''),
                'distance': getattr(r, 'distance', ''),
                'surface': getattr(r, 'surface', ''),
                'conditions': getattr(r, 'conditions', ''),
                'horses': [normalize_horse({
                    'name': getattr(h, 'name', ''),
                    'post_position': getattr(h, 'post_position', 0),
                    'jockey': getattr(h, 'jockey', ''),
                    'trainer': getattr(h, 'trainer', ''),
                    'weight': getattr(h, 'weight', 0),
                    'morning_line_odds': getattr(h, 'morning_line_odds', ''),
                    'age': getattr(h, 'age', 0),
                    'sex': getattr(h, 'sex', ''),
                    'equipment_changes': getattr(h, 'equipment_changes', ''),
                    'claiming_price': getattr(h, 'claiming_price', ''),
                    'profile_url': getattr(h, 'profile_url', ''),
                }) for h in getattr(r, 'horses', [])]
            } for r in overview_result.get('races', [])]
            with open(card_path, 'w') as f:
                json.dump({'date': date_str, 'races': races_data}, f, indent=2)
            return {'date': date_str, 'races': races_data}
    except Exception as e:
        print(f"Could not scrape race card for {date_str}: {e}")
    return {}


def extract_horses_with_profile_urls(card: Dict) -> List[Tuple[str, str]]:
    """Extract horse names and profile URLs from race card (no MAX_HORSES limit)."""
    horses_with_urls = []
    for race in card.get('races', []):
        for horse in race.get('horses', []):
            name = (horse.get('name') or '').strip()
            profile_url = (horse.get('profile_url') or '').strip()
            if name and profile_url:
                horses_with_urls.append((name, profile_url))
    return horses_with_urls


async def scrape_full_card_playwright() -> Dict[str, Dict]:
    """Scrape all horses using entry pages to determine per-race horse counts first."""
    print("Loading race card...")
    card = load_race_card()
    if not card:
        print("No race card found; cannot proceed")
        return {}

    # Determine horse list per race from the card overview (viewe2)
    date_str = os.environ.get('RACE_DATE_STR', '09/05/2025')
    entry_scraper = RaceEntryScraper()
    horses_with_urls: List[Tuple[str, str]] = []

    try:
        overview = await entry_scraper.scrape_card_overview('DMR', date_str, 'USA')
        per_race = overview.get('races', []) if isinstance(overview, dict) else []
        # Build mapping from race -> set(name)
        allow: Dict[int, set] = {}
        for r in per_race:
            rn = int(r.get('race_number'))
            allow[rn] = { (h.get('name') or '').strip() for h in r.get('horses', []) }
        # Cross-match with card profile URLs to collect URLs for allowed names
        for race in card.get('races', []):
            rn = int(race.get('race_number') or race.get('number'))
            names = allow.get(rn, set())
            for h in race.get('horses', []):
                name = (h.get('name') or '').strip()
                url = (h.get('profile_url') or '').strip()
                if name in names and name and url:
                    horses_with_urls.append((name, url))
    except Exception:
        # Hard fallback to all card horses if overview fails
        for race in card.get('races', []):
            for h in race.get('horses', []):
                name = (h.get('name') or '').strip()
                url = (h.get('profile_url') or '').strip()
                if name and url:
                    horses_with_urls.append((name, url))

    print(f"Prepared {len(horses_with_urls)} horses with profile URLs after overview verification")

    if not horses_with_urls:
        print("No horses with profile URLs found; aborting")
        return {}

    # Limit horses to prevent timeouts on Render.com (can be removed for local testing)
    MAX_HORSES = int(os.environ.get('MAX_HORSES', '50'))  # Default to 50 horses max
    if len(horses_with_urls) > MAX_HORSES:
        print(f"⚠️  Limiting to {MAX_HORSES} horses (from {len(horses_with_urls)}) to prevent timeouts")
        horses_with_urls = horses_with_urls[:MAX_HORSES]

    print("Starting Playwright scraping...")
    async with PlaywrightEquibaseScraper() as scraper:
        results = await scraper.scrape_multiple_horses(horses_with_urls)

    # Merge SmartPick per-race data for the same date to compute OUR speed
    try:
        from scrapers.smartpick_scraper import SmartPickRaceScraper
        sps = SmartPickRaceScraper(headless=True)
        try:
            date_str = os.environ.get('RACE_DATE_STR', '09/05/2025')
            # Find all race numbers from overview again to avoid mismatch
            overview = await RaceEntryScraper().scrape_card_overview('DMR', date_str, 'USA')
            races = [int(r.get('race_number')) for r in overview.get('races', [])]
            for rn in races:
                sp = sps.scrape_race('DMR', date_str, rn, 'D')
                for name, spdata in sp.items():
                    if name in results:
                        # Merge smartpick block
                        res = results[name]
                        spb = spdata.get('smartpick', {})
                        res['smartpick'] = {**(res.get('smartpick', {})), **spb}
                        # If SmartPick computed OUR speed, propagate to top level
                        if isinstance(spb.get('our_speed_figure'), (int, float)):
                            res['our_speed_figure'] = spb['our_speed_figure']
        finally:
            sps.close()
    except Exception as e:
        print(f"SmartPick merge skipped due to error: {e}")

    return results


def save_results(results: Dict[str, Dict]):
    """Save results to real_equibase_horse_data.json"""
    output_path = "real_equibase_horse_data.json"
    
    # Load existing data
    existing = {}
    if os.path.exists(output_path):
        try:
            with open(output_path, 'r') as f:
                existing = json.load(f)
        except Exception:
            existing = {}
    
    # Merge new results
    existing.update(results)
    
    # Save updated data
    with open(output_path, 'w') as f:
        json.dump(existing, f, indent=2)
    
    print(f"Saved {len(results)} horses to {output_path}")


async def main():
    """Main entry point for Playwright-based scraping"""
    try:
        results = await scrape_full_card_playwright()
        
        if results:
            save_results(results)
            
            # Print summary
            print(f"\n=== Scraping Summary ===")
            print(f"Successfully scraped: {len(results)} horses")
            
            for horse_name, data in results.items():
                results_count = len(data.get('last3_results', []))
                workouts_count = len(data.get('workouts_last3', []))
                quality = data.get('quality_rating', 0)
                print(f"  {horse_name}: {results_count} results, {workouts_count} workouts, quality={quality}")
        else:
            print("No horses were successfully scraped")
            
    except Exception as e:
        print(f"Error during scraping: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
