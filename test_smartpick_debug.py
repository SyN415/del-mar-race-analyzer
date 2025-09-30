#!/usr/bin/env python3
"""
Debug script to test SmartPick scraping and see what's actually being returned
"""
import asyncio
import sys
from scrapers.smartpick_playwright import PlaywrightSmartPickScraper

async def test_smartpick(track_id: str, race_date: str, race_number: int):
    """Test SmartPick scraping with detailed output"""
    print(f"\n{'='*60}")
    print(f"Testing SmartPick Scraper")
    print(f"{'='*60}")
    print(f"Track: {track_id}")
    print(f"Date: {race_date}")
    print(f"Race: {race_number}")
    print(f"{'='*60}\n")
    
    async with PlaywrightSmartPickScraper() as scraper:
        result = await scraper.scrape_race(track_id, race_date, race_number, "D")
        
        print(f"\n{'='*60}")
        print(f"RESULTS")
        print(f"{'='*60}")
        print(f"Found {len(result)} horses")
        
        if result:
            print(f"\nHorses found:")
            for i, (name, data) in enumerate(result.items(), 1):
                print(f"  {i}. {name}")
                if 'smartpick' in data:
                    sp = data['smartpick']
                    print(f"     Speed Figure: {sp.get('speed_figure', 'N/A')}")
                    print(f"     Jockey/Trainer Win %: {sp.get('jockey_trainer_win_pct', 'N/A')}")
        else:
            print("\n❌ No horses found!")
            print("\nCheck the logs/html directory for:")
            print(f"  - smartpick_playwright_{track_id}_r{race_number}.html")
            print(f"  - smartpick_playwright_{track_id}_r{race_number}.png")
            print("\nThese files will show what the page actually looked like.")
        
        print(f"\n{'='*60}\n")
        
        return result

if __name__ == "__main__":
    # Default test values
    track_id = sys.argv[1] if len(sys.argv) > 1 else "SA"
    race_date = sys.argv[2] if len(sys.argv) > 2 else "09/28/2024"  # Note: Changed to 2024
    race_number = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    
    print(f"\nUsage: python test_smartpick_debug.py [TRACK] [DATE] [RACE]")
    print(f"Example: python test_smartpick_debug.py SA 09/28/2024 1")
    print(f"\nUsing: {track_id} {race_date} Race {race_number}\n")
    
    asyncio.run(test_smartpick(track_id, race_date, race_number))

