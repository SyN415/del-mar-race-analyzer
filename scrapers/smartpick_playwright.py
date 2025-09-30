#!/usr/bin/env python3
"""
Playwright-based SmartPick scraper to bypass Incapsula WAF.
Replaces the requests-based SmartPickRaceScraper with Playwright.
Includes 2Captcha integration for solving hCaptcha challenges.
"""
import asyncio
import logging
import re
from typing import Dict, List, Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Import captcha solver
try:
    from services.captcha_solver import get_captcha_solver, solve_equibase_captcha
    CAPTCHA_SOLVER_AVAILABLE = True
except ImportError:
    logger.warning("⚠️  Captcha solver not available - captcha challenges will fail")
    CAPTCHA_SOLVER_AVAILABLE = False


class PlaywrightSmartPickScraper:
    """Playwright-based SmartPick scraper that bypasses WAF and solves captchas"""

    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.captcha_solver = get_captcha_solver() if CAPTCHA_SOLVER_AVAILABLE else None
        self.session_established = False
    
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

            # CRITICAL: Visit homepage first to establish session and solve captcha
            if not self.session_established:
                logger.info("🏠 Visiting Equibase homepage to establish session...")
                try:
                    await page.goto('https://www.equibase.com', wait_until='domcontentloaded', timeout=30000)
                    await page.wait_for_timeout(2000)

                    # Solve captcha if present
                    if CAPTCHA_SOLVER_AVAILABLE and self.captcha_solver:
                        captcha_solved = await solve_equibase_captcha(page, self.captcha_solver)
                        if captcha_solved:
                            logger.info("✅ Session established with captcha solved")
                            self.session_established = True
                        else:
                            logger.error("❌ Failed to solve captcha on homepage")
                            return {}
                    else:
                        logger.warning("⚠️  No captcha solver available - proceeding without solving")

                    # Accept cookies
                    try:
                        cookie_button = await page.query_selector('#onetrust-accept-btn-handler')
                        if cookie_button:
                            await cookie_button.click()
                            logger.info("🍪 Accepted cookies")
                            await page.wait_for_timeout(1000)
                    except Exception as e:
                        logger.info(f"ℹ️  No cookie banner or already accepted: {e}")
                except Exception as e:
                    logger.warning(f"⚠️  Could not visit homepage: {e}")
            else:
                logger.info("ℹ️  Session already established, skipping homepage visit")

            # Now navigate to SmartPick page
            logger.info(f"🎯 Navigating to SmartPick page...")
            response = await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            logger.info(f"📡 HTTP Status: {response.status}")

            # Check for captcha on SmartPick page
            if CAPTCHA_SOLVER_AVAILABLE and self.captcha_solver:
                await page.wait_for_timeout(2000)
                captcha_solved = await solve_equibase_captcha(page, self.captcha_solver)
                if not captcha_solved:
                    logger.warning("⚠️  Captcha present on SmartPick page but not solved")

            # Wait for network to be idle after captcha solving
            try:
                await page.wait_for_load_state('networkidle', timeout=10000)
            except Exception as e:
                logger.warning(f"⚠️  Network did not reach idle state: {e}")

            # Wait for Angular/React to render - much longer timeout
            logger.info("⏳ Waiting for JavaScript to render horse data...")
            await page.wait_for_timeout(8000)

            # Try multiple selectors that might contain horse data
            horse_data_loaded = False
            selectors_to_try = [
                'a[href*="Results.cfm"]',
                'a[href*="type=Horse"]',
                'table tr:nth-child(2)',  # Wait for data rows in tables
                '[ng-repeat]',  # Angular
                '[data-horse]',  # Common data attribute
                '.horse-name',
                '.runner'
            ]

            for selector in selectors_to_try:
                try:
                    await page.wait_for_selector(selector, timeout=3000)
                    logger.info(f"✅ Found content with selector: {selector}")
                    horse_data_loaded = True
                    break
                except Exception:
                    continue

            if not horse_data_loaded:
                logger.warning("⚠️  No horse data selectors found - trying longer wait")
                # Wait even longer for AJAX to complete
                await page.wait_for_timeout(10000)

                # Check network activity
                logger.info("🌐 Checking for AJAX requests...")
                await page.wait_for_load_state('networkidle', timeout=10000)
            
            # Try to extract data via JavaScript before getting HTML
            logger.info("🔍 Attempting to extract data via JavaScript...")
            try:
                # Check if Angular is present
                angular_data = await page.evaluate('''
                    () => {
                        // Try to find Angular scope
                        const angularElement = document.querySelector('[ng-controller], [ng-app]');
                        if (angularElement && window.angular) {
                            const scope = window.angular.element(angularElement).scope();
                            if (scope && scope.horses) {
                                return { source: 'angular', horses: scope.horses };
                            }
                        }

                        // Try to find horse links in DOM
                        const horseLinks = Array.from(document.querySelectorAll('a[href*="Results.cfm"]'));
                        if (horseLinks.length > 0) {
                            return {
                                source: 'dom',
                                count: horseLinks.length,
                                samples: horseLinks.slice(0, 5).map(a => ({
                                    text: a.textContent.trim(),
                                    href: a.href
                                }))
                            };
                        }

                        return { source: 'none', message: 'No horse data found' };
                    }
                ''')
                logger.info(f"📊 JavaScript extraction result: {angular_data}")
            except Exception as e:
                logger.warning(f"⚠️  JavaScript extraction failed: {e}")

            # Get HTML content
            html = await page.content()
            logger.info(f"📄 Response length: {len(html)} bytes")

            # Get page title for debugging
            title = await page.title()
            logger.info(f"📰 Page title: {title}")

            # Check for specific text that indicates the page loaded correctly
            page_text = await page.evaluate('() => document.body.innerText')
            if 'SmartPick' in page_text or 'smartpick' in page_text.lower():
                logger.info("✅ SmartPick content detected in page")
            else:
                logger.warning("⚠️  No SmartPick content detected - page may not have loaded correctly")
                logger.info(f"📝 First 500 chars of page text: {page_text[:500]}")

            # Check for "no data" messages
            page_text_lower = page_text.lower()
            if any(msg in page_text_lower for msg in ['no entries', 'no races', 'not available', 'no data', 'no results']):
                logger.warning("⚠️  Page indicates no race data available")
                logger.info(f"📝 Page text snippet: {page_text[:1000]}")

            # Try scrolling to trigger lazy loading
            try:
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await page.wait_for_timeout(2000)
                logger.info("📜 Scrolled page to trigger lazy loading")
            except Exception as e:
                logger.warning(f"⚠️  Could not scroll page: {e}")

            # Look for specific SmartPick table or container
            try:
                smartpick_container = await page.query_selector('.smartpick-container, #smartpick, [class*="smartpick"], [id*="smartpick"]')
                if smartpick_container:
                    logger.info("✅ Found SmartPick container element")
                else:
                    logger.warning("⚠️  No SmartPick container element found")
            except Exception as e:
                logger.warning(f"⚠️  Error looking for SmartPick container: {e}")
            
            # Save HTML and screenshot for debugging
            try:
                import os
                os.makedirs('logs/html', exist_ok=True)
                with open(f'logs/html/smartpick_playwright_{track_id}_r{race_number}.html', 'w', encoding='utf-8') as f:
                    f.write(html)
                logger.info(f"📝 Saved HTML to logs/html/smartpick_playwright_{track_id}_r{race_number}.html")

                # Take screenshot
                await page.screenshot(path=f'logs/html/smartpick_playwright_{track_id}_r{race_number}.png', full_page=True)
                logger.info(f"📸 Saved screenshot to logs/html/smartpick_playwright_{track_id}_r{race_number}.png")
            except Exception as e:
                logger.warning(f"⚠️  Could not save HTML/screenshot: {e}")
            
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

        # Debug: Show sample of link hrefs to understand structure
        sample_hrefs = [a.get('href', '')[:100] for a in horse_links[:20]]
        logger.info(f"📋 Sample hrefs: {sample_hrefs}")

        # Look for Results.cfm links
        results_links = [a for a in horse_links if 'Results.cfm' in a.get('href', '')]
        logger.info(f"🔗 Found {len(results_links)} Results.cfm links")

        # Look for type=Horse links
        horse_type_links = [a for a in horse_links if 'type=Horse' in a.get('href', '')]
        logger.info(f"🐴 Found {len(horse_type_links)} type=Horse links")

        # Look for any horse-related patterns
        horse_patterns = ['horse', 'Horse', 'HORSE', 'refno=', 'registry=']
        pattern_links = [a for a in horse_links if any(p in a.get('href', '') for p in horse_patterns)]
        logger.info(f"🔍 Found {len(pattern_links)} links with horse-related patterns")
        if pattern_links:
            logger.info(f"📋 Sample horse-pattern hrefs: {[a.get('href', '')[:100] for a in pattern_links[:5]]}")

        # Combined filter
        results_links = [a for a in horse_links if 'Results.cfm' in a.get('href', '') and 'type=Horse' in a.get('href', '')]
        logger.info(f"🐎 Found {len(results_links)} horse profile links (Results.cfm + type=Horse)")

        # Check for tables with horse data
        tables = soup.find_all('table')
        logger.info(f"📊 Found {len(tables)} tables on page")
        if tables:
            for i, table in enumerate(tables[:3]):  # Check first 3 tables
                rows = table.find_all('tr')
                logger.info(f"  Table {i+1}: {len(rows)} rows")
                if rows:
                    first_row_text = rows[0].get_text(strip=True)[:100]
                    logger.info(f"    First row: {first_row_text}")
        
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

