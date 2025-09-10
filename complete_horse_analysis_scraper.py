#!/usr/bin/env python3
"""
Complete horse analysis scraper that combines:
1. SmartPick data (speed figures, J/T percentages, earnings)
2. Individual horse workout data from profile pages
3. Past performance E values
4. Custom speed score calculation
"""

import asyncio
import json
import re
import sys
import os
from typing import Dict, List, Optional
from statistics import mean

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scrapers.playwright_equibase_scraper import PlaywrightEquibaseScraper

def calculate_speed_score(smartpick_figure: Optional[int], e_values: List[int]) -> Optional[float]:
    """Calculate custom speed score: (SmartPick Speed Figure + Average of last 3 E values) / 2"""
    if not smartpick_figure and not e_values:
        return 0.0  # Debut horse
    
    if not smartpick_figure:  # Only E values available
        return mean(e_values) if e_values else 0.0
    
    if not e_values:  # Only SmartPick figure available
        return float(smartpick_figure)
    
    # Take last 3 E values (or all if less than 3)
    recent_e_values = e_values[-3:] if len(e_values) >= 3 else e_values
    avg_e = mean(recent_e_values)
    
    return (smartpick_figure + avg_e) / 2

def extract_horse_profile_urls_from_smartpick(smartpick_data: Dict) -> List[tuple]:
    """Extract horse names and profile URLs from SmartPick data"""
    horses_with_urls = []
    
    # This would need to be implemented based on the actual SmartPick data structure
    # For now, we'll need to manually construct profile URLs or extract them from the HTML
    
    return horses_with_urls

async def scrape_complete_race_data(race_number: int) -> Dict:
    """Scrape complete race data including SmartPick and individual horse workouts"""
    
    async with PlaywrightEquibaseScraper() as scraper:
        print(f"🏁 Scraping Race {race_number} complete data...")
        
        # Step 1: Get SmartPick data
        print(f"  📊 Getting SmartPick data...")
        smartpick_data = await scraper.scrape_smartpick_data('DMR', '09/05/2025', race_number)
        
        # Step 2: Extract horse profile URLs from SmartPick page
        # We need to navigate to the SmartPick page and extract profile URLs
        smartpick_url = f"https://www.equibase.com/smartPick/smartPick.cfm/?trackId=DMR&raceDate=09%2F05%2F2025&country=USA&dayEvening=D&raceNumber={race_number}"
        
        if not scraper.context:
            await scraper.create_stealth_context()
        
        page = await scraper.context.new_page()
        await page.goto(smartpick_url, wait_until="domcontentloaded")
        await scraper.human_like_delay(3000, 5000)
        
        # Extract horse profile URLs from the page
        profile_links = await page.evaluate('''
            () => {
                const links = [];
                const anchors = document.querySelectorAll('a[href*="Results.cfm"]');
                
                for (const anchor of anchors) {
                    const href = anchor.href;
                    const name = anchor.textContent.trim();
                    
                    if (href.includes('type=Horse') && name) {
                        links.push({
                            name: name,
                            url: href
                        });
                    }
                }
                
                return links;
            }
        ''')
        
        await page.close()
        
        print(f"  🐎 Found {len(profile_links)} horse profile links")
        
        # Step 3: Scrape individual horse profiles with workouts
        horse_data = {}
        
        for i, horse_link in enumerate(profile_links):
            horse_name = horse_link['name']
            profile_url = horse_link['url']
            
            print(f"    🔍 Scraping {horse_name} ({i+1}/{len(profile_links)})...")
            
            try:
                # Scrape horse profile including workouts
                horse_profile = await scraper.scrape_horse_profile(horse_name, profile_url)
                
                if "error" not in horse_profile:
                    # Extract E values from results
                    e_values = []
                    for result in horse_profile.get('last3_results', []):
                        speed_score = result.get('speed_score')
                        if speed_score and isinstance(speed_score, (int, float)):
                            e_values.append(int(speed_score))
                    
                    # Calculate custom speed score
                    # We need to get the SmartPick speed figure for this horse
                    smartpick_figure = None  # This would come from parsing SmartPick data
                    
                    speed_score = calculate_speed_score(smartpick_figure, e_values)
                    
                    horse_data[horse_name] = {
                        **horse_profile,
                        'e_values': e_values,
                        'custom_speed_score': speed_score,
                        'profile_url': profile_url
                    }
                    
                    print(f"      ✅ {len(horse_profile.get('last3_results', []))} results, {len(horse_profile.get('workouts_last3', []))} workouts")
                else:
                    print(f"      ❌ Error: {horse_profile['error']}")
                    
            except Exception as e:
                print(f"      ❌ Exception scraping {horse_name}: {e}")
            
            # Rate limiting
            if i < len(profile_links) - 1:
                await scraper.human_like_delay(2000, 4000)
        
        return {
            'race_number': race_number,
            'smartpick_data': smartpick_data,
            'horse_data': horse_data,
            'total_horses': len(horse_data)
        }

async def scrape_full_card_with_workouts():
    """Scrape complete card data including workouts for all horses"""
    
    print("🏇 DEL MAR COMPLETE CARD SCRAPING WITH WORKOUTS")
    print("=" * 60)
    
    all_race_data = {}
    
    # Scrape races 1-8
    for race_num in range(1, 9):
        try:
            race_data = await scrape_complete_race_data(race_num)
            all_race_data[race_num] = race_data
            
            print(f"✅ Race {race_num}: {race_data['total_horses']} horses scraped")
            
        except Exception as e:
            print(f"❌ Error scraping Race {race_num}: {e}")
            all_race_data[race_num] = {
                'race_number': race_num,
                'error': str(e),
                'horse_data': {}
            }
        
        # Delay between races
        await asyncio.sleep(3)
    
    # Save complete data
    output_file = 'complete_del_mar_data_with_workouts_09_05_2025.json'
    with open(output_file, 'w') as f:
        json.dump(all_race_data, f, indent=2)
    
    print(f"\n💾 Complete data saved to: {output_file}")
    
    return all_race_data

def generate_workout_analysis(workouts: List[Dict]) -> Dict:
    """Analyze workout data for a horse"""
    if not workouts:
        return {
            'workout_count': 0,
            'recent_workout': None,
            'workout_quality': 'No workouts'
        }
    
    recent_workout = workouts[0] if workouts else None
    
    # Analyze workout times and conditions
    workout_scores = []
    for workout in workouts[:3]:  # Last 3 workouts
        time_str = workout.get('time', '')
        distance = workout.get('distance', '')
        
        # Simple workout scoring based on time
        score = 50  # Base score
        
        if ':' in time_str:
            try:
                parts = time_str.split(':')
                if len(parts) == 2:
                    minutes = int(parts[0])
                    seconds = float(parts[1])
                    total_seconds = minutes * 60 + seconds
                    
                    # Faster times get higher scores
                    if total_seconds < 60:  # Under 1 minute
                        score += 20
                    elif total_seconds < 75:  # Under 1:15
                        score += 10
            except:
                pass
        
        workout_scores.append(score)
    
    avg_workout_score = mean(workout_scores) if workout_scores else 50
    
    return {
        'workout_count': len(workouts),
        'recent_workout': recent_workout,
        'avg_workout_score': round(avg_workout_score, 1),
        'workout_quality': 'Good' if avg_workout_score > 60 else 'Average' if avg_workout_score > 40 else 'Poor'
    }

async def main():
    """Main function"""
    try:
        complete_data = await scrape_full_card_with_workouts()
        
        print("\n🎯 SCRAPING COMPLETE!")
        print(f"📊 Total races scraped: {len(complete_data)}")
        
        total_horses = sum(race.get('total_horses', 0) for race in complete_data.values())
        print(f"🐎 Total horses with workout data: {total_horses}")
        
        return complete_data
        
    except Exception as e:
        print(f"❌ Pipeline failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
