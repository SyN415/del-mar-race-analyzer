#!/usr/bin/env python3
"""
Quick test to fix the scraper and verify it's working
"""

import asyncio
import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def main():
    print("🔧 Testing and fixing Del Mar scraper...")
    
    # Set the correct date
    os.environ['RACE_DATE_STR'] = '09/07/2025'
    
    # Remove old files with placeholder data
    old_files = [
        'del_mar_09_05_2025_races.json',
        'del_mar_09_07_2025_races.json'
    ]
    
    for file in old_files:
        if os.path.exists(file):
            os.remove(file)
            print(f"🗑️  Removed old file: {file}")
    
    # Test the race entry scraper directly
    print("\n🧪 Testing RaceEntryScraper...")
    from race_entry_scraper import RaceEntryScraper
    
    scraper = RaceEntryScraper()
    url = scraper.build_card_overview_url('DMR', '09/07/2025', 'USA')
    print(f"📍 URL: {url}")
    
    try:
        result = await scraper.scrape_card_overview('DMR', '09/07/2025', 'USA')
        
        if result and result.get('races'):
            print(f"✅ Found {len(result['races'])} races")
            
            # Check for real URLs
            real_urls = 0
            total_horses = 0
            
            for race in result['races']:
                horses = race.get('horses', [])
                total_horses += len(horses)
                
                for horse in horses:
                    url = horse.get('profile_url', '')
                    if url and 'refno=' in url and 'PLACEHOLDER' not in url:
                        real_urls += 1
                        print(f"  ✅ {horse.get('name', 'Unknown')}: {url}")
                    else:
                        print(f"  ❌ {horse.get('name', 'Unknown')}: {url}")
            
            print(f"\n📊 Results: {real_urls}/{total_horses} horses have real URLs")
            
            if real_urls > 0:
                print("🎉 Scraper is working! Real URLs found.")
                
                # Test SmartPick URL format
                print(f"\n🎯 SmartPick URL test:")
                smartpick_url = f"https://www.equibase.com/smartPick/smartPick.cfm/?trackId=DMR&raceDate=09%2F07%2F2025&country=USA&dayEvening=D&raceNumber=1"
                print(f"  {smartpick_url}")
                
            else:
                print("❌ No real URLs found - scraper needs debugging")
                
        else:
            print("❌ No races found in scraper result")
            
    except Exception as e:
        print(f"❌ Scraper failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n🔧 Testing complete!")

if __name__ == "__main__":
    asyncio.run(main())
