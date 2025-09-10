#!/usr/bin/env python3
"""
Direct SmartPick API scraper that calls the discovered endpoints.
"""
import asyncio
import json
from scrapers.playwright_equibase_scraper import PlaywrightEquibaseScraper

async def scrape_smartpick_api_data():
    """Scrape SmartPick data directly from the API endpoints"""
    async with PlaywrightEquibaseScraper() as scraper:
        print("🎯 Direct SmartPick API Scraping")
        print("=" * 50)
        
        # The API endpoints discovered from network monitoring
        betting_api_url = "https://app.equibase.com/data/betting/races/08-24-2025/DMR/1"
        entry_api_url = "https://app.equibase.com/data/entry/races/08-24-2025/USA/DMR"
        
        # First, navigate to the SmartPick page to establish session/cookies
        smartpick_page_url = "https://www.equibase.com/smartPick/smartPick.cfm/?trackId=DMR&raceDate=08%2F24%2F2025&country=USA&dayEvening=D&raceNumber=1"
        
        print(f"🔐 Establishing session by visiting SmartPick page...")
        await scraper.page.goto(smartpick_page_url, wait_until='networkidle')
        await scraper.page.wait_for_timeout(3000)  # Let it load
        print("✅ Session established")
        
        # Now make direct API calls using the browser context (with cookies)
        print(f"\n📊 Fetching SmartPick betting data...")
        print(f"URL: {betting_api_url}")
        
        try:
            # Navigate to the betting API endpoint
            betting_response = await scraper.page.goto(betting_api_url, wait_until='networkidle')
            
            if betting_response.status == 200:
                betting_content = await scraper.page.content()
                print(f"✅ Betting API response: {len(betting_content)} characters")
                
                # Try to extract JSON from the response
                try:
                    # Look for JSON content in the page
                    json_content = await scraper.page.evaluate('() => document.body.textContent')
                    betting_data = json.loads(json_content)
                    
                    print(f"✅ Successfully parsed betting JSON data!")
                    print(f"Keys in betting data: {list(betting_data.keys()) if isinstance(betting_data, dict) else 'Not a dict'}")
                    
                    # Save betting data
                    with open('smartpick_betting_data.json', 'w') as f:
                        json.dump(betting_data, f, indent=2)
                    print("💾 Saved betting data to smartpick_betting_data.json")
                    
                except json.JSONDecodeError as e:
                    print(f"❌ Failed to parse betting data as JSON: {e}")
                    print(f"Raw content preview: {json_content[:200]}...")
                    
                    # Save raw content for inspection
                    with open('smartpick_betting_raw.txt', 'w') as f:
                        f.write(json_content)
                    print("💾 Saved raw betting content to smartpick_betting_raw.txt")
                    
            else:
                print(f"❌ Betting API failed with status: {betting_response.status}")
                
        except Exception as e:
            print(f"❌ Error fetching betting data: {e}")
        
        # Now fetch the entry data
        print(f"\n🏇 Fetching race entry data...")
        print(f"URL: {entry_api_url}")
        
        try:
            entry_response = await scraper.page.goto(entry_api_url, wait_until='networkidle')
            
            if entry_response.status == 200:
                entry_content = await scraper.page.content()
                print(f"✅ Entry API response: {len(entry_content)} characters")
                
                try:
                    json_content = await scraper.page.evaluate('() => document.body.textContent')
                    entry_data = json.loads(json_content)
                    
                    print(f"✅ Successfully parsed entry JSON data!")
                    print(f"Keys in entry data: {list(entry_data.keys()) if isinstance(entry_data, dict) else 'Not a dict'}")
                    
                    # Save entry data
                    with open('smartpick_entry_data.json', 'w') as f:
                        json.dump(entry_data, f, indent=2)
                    print("💾 Saved entry data to smartpick_entry_data.json")
                    
                except json.JSONDecodeError as e:
                    print(f"❌ Failed to parse entry data as JSON: {e}")
                    print(f"Raw content preview: {json_content[:200]}...")
                    
                    # Save raw content for inspection
                    with open('smartpick_entry_raw.txt', 'w') as f:
                        f.write(json_content)
                    print("💾 Saved raw entry content to smartpick_entry_raw.txt")
                    
            else:
                print(f"❌ Entry API failed with status: {entry_response.status}")
                
        except Exception as e:
            print(f"❌ Error fetching entry data: {e}")
        
        print(f"\n🎯 SmartPick API scraping complete!")
        return True

async def analyze_smartpick_data():
    """Analyze the scraped SmartPick data"""
    print("\n📈 Analyzing SmartPick Data")
    print("=" * 30)
    
    # Check if we have betting data
    try:
        with open('smartpick_betting_data.json', 'r') as f:
            betting_data = json.load(f)
        
        print("✅ Betting data loaded successfully")
        
        # Analyze betting data structure
        if isinstance(betting_data, dict):
            for key, value in betting_data.items():
                if isinstance(value, list):
                    print(f"  {key}: {len(value)} items")
                elif isinstance(value, dict):
                    print(f"  {key}: {len(value)} keys")
                else:
                    print(f"  {key}: {type(value).__name__}")
        
        # Look for horse-related data
        def find_horses_in_data(data, path=""):
            horses = []
            if isinstance(data, dict):
                for key, value in data.items():
                    current_path = f"{path}.{key}" if path else key
                    if 'horse' in key.lower() or 'runner' in key.lower():
                        print(f"🐎 Found horse data at: {current_path}")
                        horses.extend(find_horses_in_data(value, current_path))
                    else:
                        horses.extend(find_horses_in_data(value, current_path))
            elif isinstance(data, list):
                for i, item in enumerate(data):
                    horses.extend(find_horses_in_data(item, f"{path}[{i}]"))
            return horses
        
        find_horses_in_data(betting_data)
        
    except FileNotFoundError:
        print("❌ No betting data file found")
    except Exception as e:
        print(f"❌ Error analyzing betting data: {e}")
    
    # Check if we have entry data
    try:
        with open('smartpick_entry_data.json', 'r') as f:
            entry_data = json.load(f)
        
        print("✅ Entry data loaded successfully")
        
        # Analyze entry data structure
        if isinstance(entry_data, dict):
            for key, value in entry_data.items():
                if isinstance(value, list):
                    print(f"  {key}: {len(value)} items")
                elif isinstance(value, dict):
                    print(f"  {key}: {len(value)} keys")
                else:
                    print(f"  {key}: {type(value).__name__}")
        
        find_horses_in_data(entry_data)
        
    except FileNotFoundError:
        print("❌ No entry data file found")
    except Exception as e:
        print(f"❌ Error analyzing entry data: {e}")

async def main():
    """Main function"""
    success = await scrape_smartpick_api_data()
    
    if success:
        await analyze_smartpick_data()
        print("\n🎉 SmartPick API scraping completed!")
        print("Check the generated files:")
        print("  - smartpick_betting_data.json")
        print("  - smartpick_entry_data.json")
    else:
        print("❌ SmartPick API scraping failed")

if __name__ == "__main__":
    asyncio.run(main())
