#!/usr/bin/env python3
"""
Simple test script to check SmartPick URL construction using requests
"""
import requests
import sys
import re
from datetime import datetime
from urllib.parse import quote

def test_smartpick_urls(track_id: str, race_date: str, race_number: int):
    """Test different SmartPick URL formats"""
    print(f"\n{'='*60}")
    print(f"Testing SmartPick URL Construction")
    print(f"{'='*60}")
    print(f"Track: {track_id}")
    print(f"Date: {race_date}")
    print(f"Race: {race_number}")
    print(f"{'='*60}\n")
    
    # Test different URL formats
    encoded_date = quote(race_date)
    
    urls_to_test = [
        # Current format from the scraper
        f"https://www.equibase.com/smartPick/smartPick.cfm/?trackId={track_id}&raceDate={encoded_date}&country=USA&dayEvening=D&raceNumber={race_number}",
        
        # Alternative without trailing slash after .cfm
        f"https://www.equibase.com/smartPick/smartPick.cfm?trackId={track_id}&raceDate={encoded_date}&country=USA&dayEvening=D&raceNumber={race_number}",
        
        # Alternative date format (YYYY-MM-DD)
        f"https://www.equibase.com/smartPick/smartPick.cfm/?trackId={track_id}&raceDate={race_date.replace('/', '-')}&country=USA&dayEvening=D&raceNumber={race_number}",
        
        # Alternative with different parameter order
        f"https://www.equibase.com/smartPick/smartPick.cfm/?raceDate={encoded_date}&trackId={track_id}&country=USA&dayEvening=D&raceNumber={race_number}",
        
        # Test with different dayEvening value
        f"https://www.equibase.com/smartPick/smartPick.cfm/?trackId={track_id}&raceDate={encoded_date}&country=USA&dayEvening=E&raceNumber={race_number}",
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    for i, url in enumerate(urls_to_test, 1):
        print(f"\n--- Test {i}: Testing URL ---")
        print(f"URL: {url}")
        
        try:
            response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
            print(f"HTTP Status: {response.status_code}")
            
            # Check if we were redirected
            if response.url != url:
                print(f"⚠️  Redirected to: {response.url}")
            
            # Check content length
            print(f"Content length: {len(response.text)} bytes")
            
            if response.status_code == 200:
                content = response.text
                
                # Check for expected date
                date_variations = [
                    race_date,  # 10/05/2025
                    race_date.replace('/', ''),  # 10052025
                    race_date.replace('/', '-'),  # 10-05-2025
                ]
                date_found = any(d in content for d in date_variations)
                print(f"Expected date found: {date_found}")
                
                # Check for track ID
                track_found = track_id in content
                print(f"Track ID found: {track_found}")
                
                # Check for SmartPick content
                smartpick_found = 'smartpick' in content.lower()
                print(f"SmartPick content found: {smartpick_found}")
                
                # Look for horse-related links
                results_links = len(re.findall(r'Results\.cfm', content))
                horse_links = len(re.findall(r'type=Horse', content))
                print(f"Results.cfm links found: {results_links}")
                print(f"type=Horse links found: {horse_links}")
                
                # Look for any dates in the page
                dates_in_page = re.findall(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', content[:2000])
                if dates_in_page:
                    print(f"Dates found in page: {dates_in_page[:5]}")
                
                # Look for track codes
                track_codes = re.findall(r'\b[A-Z]{2,3}\b', content[:2000])
                if track_codes:
                    print(f"Track codes found: {list(set(track_codes))[:10]}")
                
                # Check for error messages
                error_indicators = [
                    'no entries', 'not available', 'no data', 'no results',
                    'no race card', 'no racing', 'not found', 'does not exist',
                    'no information available', 'no smartpick data', 'incapsula', 'imperva'
                ]
                errors_found = [msg for msg in error_indicators if msg in content.lower()]
                if errors_found:
                    print(f"⚠️  Error indicators found: {errors_found}")
                
                # Check for tables
                table_count = len(re.findall(r'<table', content))
                print(f"Tables found: {table_count}")
                
                # Save HTML for inspection
                import os
                os.makedirs('debug_output', exist_ok=True)
                with open(f'debug_output/smartpick_test_{i}_{track_id}_r{race_number}.html', 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"Saved HTML to debug_output/smartpick_test_{i}_{track_id}_r{race_number}.html")
                
                # Show first 500 chars of content
                print(f"First 500 chars: {content[:500]}")
                
            else:
                print(f"❌ HTTP Error: {response.status_code}")
                print(f"Response: {response.text[:200]}")
                
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print(f"\n{'='*60}")
    print("Test completed. Check debug_output/ directory for saved files.")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    # Default test values
    track_id = sys.argv[1] if len(sys.argv) > 1 else "SA"
    race_date = sys.argv[2] if len(sys.argv) > 2 else "10/05/2025"  # Recent Sunday
    race_number = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    
    print(f"\nUsage: python test_smartpick_urls_simple.py [TRACK] [DATE] [RACE]")
    print(f"Example: python test_smartpick_urls_simple.py SA 10/05/2025 1")
    print(f"\nUsing: {track_id} {race_date} Race {race_number}\n")
    
    test_smartpick_urls(track_id, race_date, race_number)