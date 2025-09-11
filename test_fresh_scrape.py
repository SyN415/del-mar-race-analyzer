#!/usr/bin/env python3
"""
Test script to force a fresh scrape of Del Mar race card data
This will help debug why we're getting placeholder URLs
"""

import asyncio
import json
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from race_entry_scraper import RaceEntryScraper

async def test_fresh_scrape():
    """Test fresh scraping of race card data"""
    print("🔍 Testing fresh scrape of Del Mar race card...")
    
    # Set the date we want to scrape
    date_str = '09/07/2025'
    track_code = 'DMR'
    country = 'USA'
    
    print(f"📅 Scraping date: {date_str}")
    print(f"🏁 Track: {track_code}")
    
    # Remove any existing race card file to force fresh scrape
    old_file = f"del_mar_{date_str.replace('/', '_')}_races.json"
    if os.path.exists(old_file):
        os.remove(old_file)
        print(f"🗑️  Removed old race card file: {old_file}")
    
    # Create scraper and test the URL building
    scraper = RaceEntryScraper()
    overview_url = scraper.build_card_overview_url(track_code, date_str, country)
    print(f"🌐 Overview URL: {overview_url}")
    
    # Test scraping
    try:
        print("🚀 Starting scrape...")
        result = await scraper.scrape_card_overview(track_code, date_str, country)
        
        if not result:
            print("❌ No result returned from scraper")
            return
        
        print(f"✅ Scrape completed!")
        print(f"📊 Total races found: {result.get('total_races', 0)}")
        
        # Check the races data
        races = result.get('races', [])
        if not races:
            print("❌ No races found in result")
            return
        
        print("\n📋 Race Summary:")
        total_horses = 0
        horses_with_real_urls = 0
        
        for race in races:
            race_num = race.get('race_number', 0)
            horse_count = race.get('horse_count', 0)
            horses = race.get('horses', [])
            
            print(f"  Race {race_num}: {horse_count} horses")
            total_horses += horse_count
            
            # Check for real URLs vs placeholders
            for horse in horses:
                profile_url = horse.get('profile_url', '')
                if profile_url and 'PLACEHOLDER' not in profile_url and 'refno=' in profile_url:
                    horses_with_real_urls += 1
                    # Extract refno for verification
                    import re
                    refno_match = re.search(r'refno=(\d+)', profile_url)
                    if refno_match:
                        refno = refno_match.group(1)
                        print(f"    ✅ {horse.get('name', 'Unknown')}: refno={refno}")
                    else:
                        print(f"    ⚠️  {horse.get('name', 'Unknown')}: URL without refno")
                else:
                    print(f"    ❌ {horse.get('name', 'Unknown')}: {profile_url}")
        
        print(f"\n📈 Summary:")
        print(f"  Total horses: {total_horses}")
        print(f"  Horses with real URLs: {horses_with_real_urls}")
        print(f"  Success rate: {horses_with_real_urls/total_horses*100:.1f}%" if total_horses > 0 else "  Success rate: 0%")
        
        # Save the result
        if horses_with_real_urls > 0:
            # Convert to the format expected by the main system
            race_card_data = {
                'date': date_str,
                'track': track_code,
                'races': []
            }
            
            for race in races:
                race_data = {
                    'race_number': race.get('race_number', 0),
                    'post_time': '',  # Will be filled by detailed scraping
                    'race_type': '',
                    'purse': '',
                    'distance': '',
                    'surface': '',
                    'conditions': '',
                    'horses': []
                }
                
                for horse in race.get('horses', []):
                    horse_data = {
                        'name': horse.get('name', ''),
                        'post_position': 0,  # Will be filled by detailed scraping
                        'program_number': 0,
                        'age_sex': '',
                        'jockey': '',
                        'trainer': '',
                        'weight': 0,
                        'claim_price': '',
                        'morning_line': '',
                        'profile_url': horse.get('profile_url', '')
                    }
                    race_data['horses'].append(horse_data)
                
                race_card_data['races'].append(race_data)
            
            # Save to file
            filename = f"del_mar_{date_str.replace('/', '_')}_races.json"
            with open(filename, 'w') as f:
                json.dump(race_card_data, f, indent=2)
            print(f"💾 Saved race card data to: {filename}")
            
            # Test SmartPick URL building
            print(f"\n🎯 SmartPick URL examples:")
            for i in range(1, min(4, len(races) + 1)):  # Show first 3 races
                smartpick_url = f"https://www.equibase.com/smartPick/smartPick.cfm/?trackId={track_code}&raceDate={date_str.replace('/', '%2F')}&country={country}&dayEvening=D&raceNumber={i}"
                print(f"  Race {i}: {smartpick_url}")
        
        else:
            print("❌ No horses with real URLs found - scraping failed")
            
    except Exception as e:
        print(f"❌ Error during scraping: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_fresh_scrape())
