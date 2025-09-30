#!/usr/bin/env python3
"""
Playwright-based SmartPick scraper to bypass Incapsula WAF.
Replaces the requests-based SmartPickRaceScraper with Playwright.
"""
import asyncio
import logging
import re
from typing import Dict, List, Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class PlaywrightSmartPickScraper:
    """Playwright-based SmartPick scraper that bypasses WAF"""
    
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled'
            ]
        )
        self.context = await self.browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='en-US',
            timezone_id='America/Los_Angeles'
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def scrape_race(self, track_id: str, race_date: str, race_number: int, day: str = "D") -> Dict[str, Dict]:
        """
        Scrape SmartPick data for a single race using Playwright
        
        Args:
            track_id: Track code (e.g., 'DMR', 'SA')
            race_date: Date in MM/DD/YYYY format
            race_number: Race number (1-12)
            day: 'D' for day or 'E' for evening
            
        Returns:
            Dict mapping horse names to their data
        """
        url = f"https://www.equibase.com/smartPick/smartPick.cfm/?trackId={track_id}&raceDate={race_date}&country=USA&dayEvening={day}&raceNumber={race_number}"
        
        logger.info(f"🌐 Fetching SmartPick URL: {url}")
        
        try:
            page = await self.context.new_page()
            
            # Navigate to page
            response = await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            logger.info(f"📡 HTTP Status: {response.status}")
            
            # Wait for content to load
            await page.wait_for_timeout(3000)
            
            # Get HTML content
            html = await page.content()
            logger.info(f"📄 Response length: {len(html)} bytes")
            
            # Save HTML for debugging
            try:
                import os
                os.makedirs('logs/html', exist_ok=True)
                with open(f'logs/html/smartpick_playwright_{track_id}_r{race_number}.html', 'w', encoding='utf-8') as f:
                    f.write(html)
                logger.info(f"📝 Saved HTML to logs/html/smartpick_playwright_{track_id}_r{race_number}.html")
            except Exception as e:
                logger.warning(f"⚠️  Could not save HTML: {e}")
            
            await page.close()
            
            # Parse the HTML
            horses = self.parse_smartpick_html(html)
            logger.info(f"🐎 Found {len(horses)} horses in race {race_number}")
            
            return horses
            
        except Exception as e:
            logger.error(f"❌ Error scraping race {race_number}: {e}")
            return {}
    
    def parse_smartpick_html(self, html: str) -> Dict[str, Dict]:
        """
        Parse SmartPick HTML to extract horse data
        
        Returns:
            Dict mapping horse names to their SmartPick data
        """
        horses = {}
        
        if not html:
            logger.warning("⚠️  No HTML content to parse")
            return horses
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check for blocked/error pages
        page_text = soup.get_text().lower()
        if 'incapsula' in page_text or 'access denied' in page_text:
            logger.error("🚫 Page appears to be blocked by WAF")
            return horses
        if 'no entries' in page_text or 'not available' in page_text:
            logger.info("ℹ️  Page indicates no entries available")
            return horses
        
        # Find all horse profile links
        horse_links = soup.find_all('a', href=True)
        logger.info(f"🔍 Found {len(horse_links)} total links")
        
        results_links = [a for a in horse_links if 'Results.cfm' in a.get('href', '') and 'type=Horse' in a.get('href', '')]
        logger.info(f"🐎 Found {len(results_links)} horse profile links")
        
        for link in results_links:
            try:
                horse_name = link.get_text(strip=True)
                if not horse_name:
                    continue
                
                href = link['href']
                profile_url = href if href.startswith('http') else f"https://www.equibase.com{href if href.startswith('/') else '/' + href}"
                
                # Extract refno and registry from URL
                refno, registry = self.parse_refno_registry(profile_url)
                
                # Look for Jockey/Trainer combo win percentage
                combo_win_pct = None
                parent = link.parent
                for _ in range(3):  # Check up to 3 parent levels
                    if parent:
                        text = parent.get_text(' ', strip=True)
                        match = re.search(r'Jockey\s*/\s*Trainer\s*Win\s*%\s*(\d{1,3})%', text, re.I)
                        if match:
                            combo_win_pct = int(match.group(1))
                            break
                        parent = parent.parent
                
                horses[horse_name] = {
                    'smartpick': {
                        'combo_win_pct': combo_win_pct
                    },
                    'profile_url': profile_url,
                    'refno': refno,
                    'registry': registry
                }
                
                logger.info(f"  ✅ Parsed: {horse_name} (combo: {combo_win_pct}%)")
                
            except Exception as e:
                logger.warning(f"⚠️  Error parsing horse link: {e}")
                continue
        
        logger.info(f"📊 Total horses parsed: {len(horses)}")
        return horses
    
    def parse_refno_registry(self, url: str) -> tuple:
        """Extract refno and registry from profile URL"""
        if not url:
            return None, None
        match = re.search(r'refno=(\d+).*?registry=([A-Za-z])', url)
        if match:
            return match.group(1), match.group(2)
        return None, None


async def scrape_smartpick_with_playwright(track_id: str, race_date: str, race_number: int, day: str = "D") -> Dict[str, Dict]:
    """
    Convenience function to scrape a single race with Playwright
    
    Args:
        track_id: Track code (e.g., 'DMR', 'SA')
        race_date: Date in MM/DD/YYYY format
        race_number: Race number
        day: 'D' for day or 'E' for evening
        
    Returns:
        Dict mapping horse names to their data
    """
    async with PlaywrightSmartPickScraper() as scraper:
        return await scraper.scrape_race(track_id, race_date, race_number, day)


async def scrape_multiple_races_playwright(track_id: str, race_date: str, num_races: int, day: str = "D") -> Dict[int, Dict[str, Dict]]:
    """
    Scrape multiple races efficiently with a single browser instance
    
    Args:
        track_id: Track code
        race_date: Date in MM/DD/YYYY format
        num_races: Number of races to scrape
        day: 'D' for day or 'E' for evening
        
    Returns:
        Dict mapping race numbers to horse data
    """
    all_races = {}
    
    async with PlaywrightSmartPickScraper() as scraper:
        for race_num in range(1, num_races + 1):
            logger.info(f"📊 Scraping SmartPick Race {race_num}...")
            horses = await scraper.scrape_race(track_id, race_date, race_num, day)
            if horses:
                all_races[race_num] = horses
                logger.info(f"  ✅ Found {len(horses)} horses in race {race_num}")
            else:
                logger.warning(f"  ⚠️  No data found for race {race_num}")
            
            # Small delay between races
            await asyncio.sleep(2)
    
    return all_races


if __name__ == "__main__":
    # Test the scraper
    async def test():
        result = await scrape_smartpick_with_playwright('SA', '09/28/2025', 1, 'D')
        print(f"Found {len(result)} horses")
        for name, data in result.items():
            print(f"  {name}: {data}")
    
    asyncio.run(test())

