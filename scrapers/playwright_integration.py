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


async def scrape_overview():
    """Scrape race card overview using RaceEntryScraper"""
    try:
        date_str = os.environ.get('RACE_DATE_STR', '09/07/2025')  # Updated to 09/07/2025
        scraper = RaceEntryScraper()
        result = await scraper.scrape_card_overview('DMR', date_str, 'USA')
        return result
    except Exception as e:
        print(f"Failed to scrape overview: {e}")
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
                'race_number': r.race_number,
                'post_time': r.post_time,
                'race_type': r.race_type,
                'purse': r.purse,
                'distance': r.distance,
                'surface': r.surface,
                'conditions': r.conditions,
                'horses': [normalize_horse({
                    'name': h.name,
                    'post_position': h.post_position,
                    'jockey': h.jockey,
                    'trainer': h.trainer,
                    'weight': h.weight,
                    'morning_line_odds': h.morning_line_odds,
                    'age': h.age,
                    'sex': h.sex,
                    'equipment_changes': h.equipment_changes,
                    'claiming_price': h.claiming_price,
                    'profile_url': getattr(h, 'profile_url', ''),
                }) for h in r.horses]
            } for r in race_card.races]
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
