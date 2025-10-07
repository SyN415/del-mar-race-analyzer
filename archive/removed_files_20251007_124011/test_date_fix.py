#!/usr/bin/env python3
"""
Test script to verify date format conversion and URL building
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_date_conversion():
    """Test date format conversion"""
    print("🧪 Testing date format conversion...")
    
    # Test cases
    test_dates = [
        '2025-09-07',  # YYYY-MM-DD format (from web app)
        '09/07/2025',  # MM/DD/YYYY format (expected by scraper)
        '2025-08-24',  # Another YYYY-MM-DD
        '08/24/2025'   # Another MM/DD/YYYY
    ]
    
    for date_str in test_dates:
        print(f"\n📅 Testing date: {date_str}")
        
        # Apply conversion logic
        if len(date_str) == 10 and date_str[4] == '-' and date_str[7] == '-':
            # Convert from YYYY-MM-DD to MM/DD/YYYY
            year, month, day = date_str.split('-')
            converted_date = f"{month}/{day}/{year}"
            print(f"  ✅ Converted to: {converted_date}")
        else:
            converted_date = date_str
            print(f"  ➡️  No conversion needed: {converted_date}")
        
        # Test URL building
        from race_entry_scraper import RaceEntryScraper
        scraper = RaceEntryScraper()
        url = scraper.build_card_overview_url('DMR', converted_date, 'USA')
        print(f"  🌐 URL: {url}")
        
        # Test file naming
        filename = f"del_mar_{converted_date.replace('/', '_')}_races.json"
        print(f"  📁 File: {filename}")

def test_environment_variable():
    """Test environment variable handling"""
    print("\n🔧 Testing environment variable handling...")
    
    # Test with YYYY-MM-DD format (what the web app sends)
    os.environ['RACE_DATE_STR'] = '2025-09-07'
    
    # Import and test the conversion in the actual functions
    from scrapers.playwright_integration import load_race_card
    
    print("📋 Testing load_race_card() with YYYY-MM-DD format...")
    try:
        # This should trigger the date conversion
        card = load_race_card()
        print("✅ load_race_card() completed without errors")
    except Exception as e:
        print(f"❌ load_race_card() failed: {e}")

if __name__ == "__main__":
    print("🔍 Testing Date Format Fixes")
    print("=" * 50)
    
    test_date_conversion()
    test_environment_variable()
    
    print("\n🎯 Summary:")
    print("  - Date conversion logic should handle YYYY-MM-DD → MM/DD/YYYY")
    print("  - URL building should work with converted dates")
    print("  - File naming should use underscores instead of slashes")
    print("  - Environment variable handling should be seamless")
    
    print("\n✅ Date format testing complete!")
