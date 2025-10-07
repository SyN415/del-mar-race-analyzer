#!/usr/bin/env python3
"""
Debug script to test SmartPick URL construction and page content
"""
import asyncio
import sys
import os
from datetime import datetime
from playwright.async_api import async_playwright

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_smartpick_url(track_id: str, race_date: str, race_number: int):
    """Test SmartPick URL and check what's actually returned"""
    print(f"\n{'='*60}")
    print(f"Testing SmartPick URL Construction")
    print(f"{'='*60}")
    print(f"Track: {track_id}")
    print(f"Date: {race_date}")
    print(f"Race: {race_number}")
    print(f"{'='*60}\n")
    
    # Test different URL formats
    import urllib.parse
    encoded_date = urllib.parse.quote(race_date)
    
    urls_to_test = [
        # Current format from the scraper
        f"https://www.equibase.com/smartPick/smartPick.cfm/?trackId={track_id}&raceDate={encoded_date}&country=USA&dayEvening=D&raceNumber={race_number}",
        
        # Alternative without trailing slash after .cfm
        f"https://www.equibase.com/smartPick/smartPick.cfm?trackId={track_id}&raceDate={encoded_date}&country=USA&dayEvening=D&raceNumber={race_number}",
        
        # Alternative date format (YYYY-MM-DD)
        f"https://www.equibase.com/smartPick/smartPick.cfm/?trackId={track_id}&raceDate={race_date.replace('/', '-')}&country=USA&dayEvening=D&raceNumber={race_number}",
        
        # Alternative with different parameter order
        f"https://www.equibase.com/smartPick/smartPick.cfm/?raceDate={encoded_date}&trackId={track_id}&country=USA&dayEvening=D&raceNumber={race_number}",
    ]
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # Set to False for debugging
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        
        for i, url in enumerate(urls_to_test, 1):
            print(f"\n--- Test {i}: Testing URL ---")
            print(f"URL: {url}")
            
            page = await context.new_page()
            
            try:
                # Visit homepage first
                print("Visiting Equibase homepage...")
                await page.goto('https://www.equibase.com', wait_until='domcontentloaded', timeout=30000)
                await page.wait_for_timeout(2000)
                
                # Accept cookies if present
                try:
                    cookie_button = await page.query_selector('#onetrust-accept-btn-handler')
                    if cookie_button:
                        await cookie_button.click()
                        print("Accepted cookies")
                        await page.wait_for_timeout(1000)
                except:
                    pass
                
                # Now navigate to SmartPick page
                print(f"Navigating to SmartPick page...")
                response = await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                print(f"HTTP Status: {response.status}")
                
                # Get current URL after any redirects
                current_url = page.url
                print(f"Final URL: {current_url}")
                
                if current_url != url:
                    print(f"⚠️  Redirected from: {url}")
                    print(f"⚠️  To: {current_url}")
                
                # Get page title
                title = await page.title()
                print(f"Page title: {title}")
                
                # Check page content
                page_text = await page.evaluate('() => document.body.innerText')
                
                # Check for expected date
                date_variations = [
                    race_date,  # 09/28/2025
                    race_date.replace('/', ''),  # 09282025
                    race_date.replace('/', '-'),  # 09-28-2025
                ]
                date_found = any(d in page_text for d in date_variations)
                print(f"Expected date found: {date_found}")
                
                # Check for track ID
                track_found = track_id in page_text
                print(f"Track ID found: {track_found}")
                
                # Check for SmartPick content
                smartpick_found = 'smartpick' in page_text.lower()
                print(f"SmartPick content found: {smartpick_found}")
                
                # Look for horse-related links
                html = await page.content()
                soup = None
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Count various link types
                    all_links = soup.find_all('a', href=True)
                    results_links = [a for a in all_links if 'Results.cfm' in a.get('href', '')]
                    horse_links = [a for a in all_links if 'type=Horse' in a.get('href', '')]
                    
                    print(f"Total links found: {len(all_links)}")
                    print(f"Results.cfm links: {len(results_links)}")
                    print(f"type=Horse links: {len(horse_links)}")
                    
                    # Show sample links
                    if results_links:
                        print(f"Sample Results.cfm link: {results_links[0].get('href', '')[:100]}")
                    if horse_links:
                        print(f"Sample horse link: {horse_links[0].get('href', '')[:100]}")
                    
                    # Look for any dates in the page
                    import re
                    dates_in_page = re.findall(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', page_text[:2000])
                    if dates_in_page:
                        print(f"Dates found in page: {dates_in_page[:5]}")
                    
                    # Look for track codes
                    track_codes = re.findall(r'\b[A-Z]{2,3}\b', page_text[:2000])
                    if track_codes:
                        print(f"Track codes found: {list(set(track_codes))[:10]}")
                    
                except ImportError:
                    print("BeautifulSoup not available for detailed parsing")
                
                # Check for error messages
                error_indicators = [
                    'no entries', 'not available', 'no data', 'no results',
                    'no race card', 'no racing', 'not found', 'does not exist',
                    'no information available', 'no smartpick data'
                ]
                errors_found = [msg for msg in error_indicators if msg in page_text.lower()]
                if errors_found:
                    print(f"⚠️  Error indicators found: {errors_found}")
                
                # Save HTML for inspection
                os.makedirs('debug_output', exist_ok=True)
                with open(f'debug_output/smartpick_test_{i}_{track_id}_r{race_number}.html', 'w', encoding='utf-8') as f:
                    f.write(html)
                print(f"Saved HTML to debug_output/smartpick_test_{i}_{track_id}_r{race_number}.html")
                
                # Take screenshot
                await page.screenshot(path=f'debug_output/smartpick_test_{i}_{track_id}_r{race_number}.png', full_page=True)
                print(f"Saved screenshot to debug_output/smartpick_test_{i}_{track_id}_r{race_number}.png")
                
            except Exception as e:
                print(f"❌ Error: {e}")
            
            finally:
                await page.close()
                await page.wait_for_timeout(1000)
        
        await context.close()
        await browser.close()
    
    print(f"\n{'='*60}")
    print("Test completed. Check debug_output/ directory for saved files.")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    # Default test values
    track_id = sys.argv[1] if len(sys.argv) > 1 else "SA"
    race_date = sys.argv[2] if len(sys.argv) > 2 else "09/28/2024"  # Using 2024 for existing data
    race_number = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    
    print(f"\nUsage: python debug_smartpick_url.py [TRACK] [DATE] [RACE]")
    print(f"Example: python debug_smartpick_url.py SA 09/28/2024 1")
    print(f"\nUsing: {track_id} {race_date} Race {race_number}\n")
    
    asyncio.run(test_smartpick_url(track_id, race_date, race_number))