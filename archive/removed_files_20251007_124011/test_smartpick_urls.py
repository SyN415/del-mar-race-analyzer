#!/usr/bin/env python3
"""
Test SmartPick URL generation and basic connectivity
"""

import os
import sys
import urllib.parse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_smartpick_urls():
    """Test SmartPick URL generation for 09/07/2025"""
    print("🧪 Testing SmartPick URL Generation")
    print("=" * 50)
    
    date_str = "09/07/2025"
    track_id = "DMR"
    
    # Test URL generation for races 1-8
    for race_num in range(1, 9):
        # Manual URL building (what should happen)
        encoded_date = urllib.parse.quote(date_str, safe='')
        manual_url = f"https://www.equibase.com/smartPick/smartPick.cfm/?trackId={track_id}&raceDate={encoded_date}&country=USA&dayEvening=D&raceNumber={race_num}"
        
        # Using the smartpick_url function
        from scrapers.smartpick_scraper import smartpick_url
        function_url = smartpick_url(track_id, date_str, race_num, "D")
        
        print(f"\n🏁 Race {race_num}:")
        print(f"  Manual URL:   {manual_url}")
        print(f"  Function URL: {function_url}")
        print(f"  Match: {'✅' if manual_url == function_url else '❌'}")
        
        # Test basic connectivity (just check if URL is reachable)
        try:
            import requests
            response = requests.head(function_url, timeout=10)
            status = response.status_code
            print(f"  Status: {status} {'✅' if status == 200 else '❌'}")
        except Exception as e:
            print(f"  Status: Error - {e}")

def test_smartpick_scraper():
    """Test the SmartPick scraper directly"""
    print("\n🔧 Testing SmartPick Scraper")
    print("=" * 50)
    
    from scrapers.smartpick_scraper import SmartPickRaceScraper
    
    scraper = SmartPickRaceScraper(headless=True)
    
    # Test races 1, 3, and 5 (user said 3+ should work)
    test_races = [1, 3, 5]
    
    for race_num in test_races:
        print(f"\n🏁 Testing Race {race_num}:")
        try:
            result = scraper.scrape_race("DMR", "09/07/2025", race_num, "D")
            
            if result:
                horse_count = len(result)
                print(f"  ✅ Found {horse_count} horses")
                
                # Show first horse as example
                if result:
                    first_horse = list(result.keys())[0]
                    horse_data = result[first_horse]
                    print(f"  📊 Example: {first_horse}")
                    print(f"    SmartPick data: {horse_data.get('smartpick', {})}")
            else:
                print(f"  ❌ No data found")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
            import traceback
            traceback.print_exc()
    
    scraper.close()

def test_url_accessibility():
    """Test if SmartPick URLs are accessible manually"""
    print("\n🌐 Testing URL Accessibility")
    print("=" * 50)
    
    base_url = "https://www.equibase.com/smartPick/smartPick.cfm/?trackId=DMR&raceDate=09%2F07%2F2025&country=USA&dayEvening=D&raceNumber="
    
    for race_num in range(1, 6):
        url = base_url + str(race_num)
        print(f"\n🏁 Race {race_num}: {url}")
        
        try:
            import requests
            response = requests.get(url, timeout=15)
            
            print(f"  Status: {response.status_code}")
            
            if response.status_code == 200:
                content = response.text
                
                # Check for key indicators
                has_horses = 'Results.cfm' in content and 'type=Horse' in content
                has_error = 'error' in content.lower() or 'not found' in content.lower()
                has_data = 'Jockey' in content and 'Trainer' in content
                
                print(f"  Has horse links: {'✅' if has_horses else '❌'}")
                print(f"  Has race data: {'✅' if has_data else '❌'}")
                print(f"  Has errors: {'❌' if has_error else '✅'}")
                
                # Save sample for debugging
                if race_num == 3:  # Save race 3 as example
                    try:
                        os.makedirs('debug', exist_ok=True)
                        with open(f'debug/smartpick_race_{race_num}_sample.html', 'w') as f:
                            f.write(content)
                        print(f"  💾 Saved sample to debug/smartpick_race_{race_num}_sample.html")
                    except Exception:
                        pass
            
        except Exception as e:
            print(f"  ❌ Error: {e}")

if __name__ == "__main__":
    print("🔍 SmartPick URL and Scraper Testing")
    print("Date: 09/07/2025")
    print("Track: DMR (Del Mar)")
    print("Expected: Races 1-2 inaccessible, Races 3+ accessible")
    print()
    
    test_smartpick_urls()
    test_url_accessibility()
    test_smartpick_scraper()
    
    print("\n🎯 Summary:")
    print("- Check if URL formats are correct")
    print("- Verify which races return data vs errors")
    print("- Test if scraper can parse available races")
    print("- Debug any parsing issues")
    
    print("\n✅ SmartPick testing complete!")
